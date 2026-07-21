"""One daily paper-trading cycle. Schedule after market close (orders fill next open).

Usage: python scripts/run_live.py
The default simulated broker needs no keys. broker: alpaca_paper needs
ALPACA_API_KEY / ALPACA_SECRET_KEY in .env.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd

from diyquant.alerts.discord import DiscordNotifier, format_cycle_alert
from diyquant.config import PROJECT_ROOT, Settings, get_secrets, get_settings
from diyquant.data.providers.yfinance_provider import YFinanceProvider
from diyquant.execution.base import Broker
from diyquant.execution.ledger import Ledger
from diyquant.execution.pipeline import run_once
from diyquant.signals.sentiment.filter import ScoredHeadline, aggregate_sentiment
from diyquant.signals.technical.sma_crossover import SmaCrossover


def make_broker(settings: Settings, bars_by_symbol: dict[str, pd.DataFrame]) -> Broker:
    if settings.execution.broker == "simulated":
        from diyquant.execution.sim_broker import SimulatedBroker

        return SimulatedBroker(
            PROJECT_ROOT / settings.execution.sim_db_path,
            bars_by_symbol,
            cost_bps=settings.backtest.cost_bps,
            slippage_bps=settings.backtest.slippage_bps,
            starting_cash=settings.execution.starting_cash,
        )
    if settings.execution.broker == "alpaca_paper":
        from diyquant.execution.alpaca_broker import AlpacaBroker

        secrets = get_secrets()
        return AlpacaBroker(
            secrets.alpaca_api_key, secrets.alpaca_secret_key, paper=secrets.alpaca_paper
        )
    raise ValueError(f"unknown broker: {settings.execution.broker}")


def fetch_sentiment_scores(settings: Settings) -> dict[str, float | None]:
    """Score recent whitelisted news per ticker; None entries mean 'no signal'.

    A news/model failure must not strand the whole cycle: fall back to
    ungated (score None) and say so on stdout.
    """
    from diyquant.data.providers.yfinance_news import YFinanceNewsProvider
    from diyquant.signals.sentiment.finbert import FinbertScorer

    cfg = settings.sentiment
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=cfg.lookback_hours)
    scores: dict[str, float | None] = {}
    try:
        provider = YFinanceNewsProvider()
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

    provider = YFinanceProvider()
    bars_by_symbol = {
        ticker: provider.fetch_daily_bars(ticker, settings.data.start)
        for ticker in settings.universe["tickers"]
    }

    broker = make_broker(settings, bars_by_symbol)
    ledger = Ledger(PROJECT_ROOT / settings.execution.ledger_path)
    strategy = SmaCrossover(**settings.strategy.params)

    sentiment_scores = None
    if settings.sentiment.enabled:
        sentiment_scores = fetch_sentiment_scores(settings)

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

    # Last step on purpose: the cycle is already durably recorded, so a failed
    # alert costs visibility, never state.
    if settings.alerts.enabled:
        notifier = DiscordNotifier(
            get_secrets().discord_webhook_url,
            timeout_seconds=settings.alerts.timeout_seconds,
        )
        notifier.send(format_cycle_alert(report, settings.strategy.name))


if __name__ == "__main__":
    main()
