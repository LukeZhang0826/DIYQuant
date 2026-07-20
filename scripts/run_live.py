"""One daily paper-trading cycle. Schedule after market close (orders fill next open).

Usage: python scripts/run_live.py
Requires ALPACA_API_KEY / ALPACA_SECRET_KEY in .env (paper account).
"""

from datetime import datetime, timedelta, timezone

from diyquant.config import PROJECT_ROOT, Settings, get_secrets, get_settings
from diyquant.data.providers.yfinance_provider import YFinanceProvider
from diyquant.execution.alpaca_broker import AlpacaBroker
from diyquant.execution.ledger import Ledger
from diyquant.execution.pipeline import run_once
from diyquant.signals.sentiment.filter import ScoredHeadline, aggregate_sentiment
from diyquant.signals.technical.sma_crossover import SmaCrossover


def fetch_sentiment_scores(settings: Settings, secrets) -> dict[str, float | None]:
    """Score recent whitelisted news per ticker; None entries mean 'no signal'.

    A news/model failure must not strand the whole cycle: fall back to
    ungated (score None) and say so on stdout.
    """
    from diyquant.data.providers.alpaca_news import AlpacaNewsProvider
    from diyquant.signals.sentiment.finbert import FinbertScorer

    cfg = settings.sentiment
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=cfg.lookback_hours)
    scores: dict[str, float | None] = {}
    try:
        provider = AlpacaNewsProvider(secrets.alpaca_api_key, secrets.alpaca_secret_key)
        scorer = FinbertScorer()
        for ticker in settings.universe["tickers"]:
            items = provider.fetch_news(ticker, start)
            headline_scores = scorer.score_headlines([i.headline for i in items])
            scored = [
                ScoredHeadline(ts=i.ts, source=i.source, score=s)
                for i, s in zip(items, headline_scores)
            ]
            scores[ticker] = aggregate_sentiment(scored, now, cfg.half_life_hours, cfg.sources)
    except Exception as exc:  # noqa: BLE001 - degrade to ungated, never skip the cycle
        print(f"sentiment unavailable, trading ungated: {exc}")
        return {t: None for t in settings.universe["tickers"]}
    return scores


def main() -> None:
    settings = get_settings()
    secrets = get_secrets()

    broker = AlpacaBroker(
        secrets.alpaca_api_key, secrets.alpaca_secret_key, paper=secrets.alpaca_paper
    )
    ledger = Ledger(PROJECT_ROOT / settings.execution.ledger_path)
    provider = YFinanceProvider()
    strategy = SmaCrossover(**settings.strategy.params)

    bars_by_symbol = {
        ticker: provider.fetch_daily_bars(ticker, settings.data.start)
        for ticker in settings.universe["tickers"]
    }

    sentiment_scores = None
    if settings.sentiment.enabled:
        sentiment_scores = fetch_sentiment_scores(settings, secrets)

    report = run_once(
        broker=broker,
        ledger=ledger,
        bars_by_symbol=bars_by_symbol,
        strategy=strategy,
        strategy_name=settings.strategy.name,
        settings=settings,
        sentiment_scores=sentiment_scores,
    )
    ledger.close()
    print(report.summary())


if __name__ == "__main__":
    main()
