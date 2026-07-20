"""Print recent headlines and their FinBERT sentiment for the configured universe.

Diagnostic only, no trading. Usage: python scripts/score_news.py
First run downloads the FinBERT model (~420 MB). No API keys needed.
"""

from datetime import datetime, timedelta, timezone

from diyquant.config import get_settings
from diyquant.data.providers.yfinance_news import YFinanceNewsProvider
from diyquant.signals.sentiment.filter import ScoredHeadline, aggregate_sentiment
from diyquant.signals.sentiment.finbert import FinbertScorer


def main() -> None:
    settings = get_settings()
    cfg = settings.sentiment
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=cfg.lookback_hours)

    provider = YFinanceNewsProvider()
    scorer = FinbertScorer()

    for ticker in settings.universe["tickers"]:
        items = provider.fetch_news(ticker, start)
        scores = scorer.score_headlines([i.headline for i in items])
        print(f"\n=== {ticker} ({len(items)} headlines, last {cfg.lookback_hours}h) ===")
        for item, score in zip(items, scores):
            print(f"  {score:+.2f}  [{item.source}] {item.headline[:90]}")
        scored = [ScoredHeadline(ts=i.ts, source=i.source, score=s) for i, s in zip(items, scores)]
        agg = aggregate_sentiment(scored, now, cfg.half_life_hours, cfg.sources)
        print(f"  aggregate: {'n/a (no whitelisted news)' if agg is None else f'{agg:+.2f}'}")


if __name__ == "__main__":
    main()
