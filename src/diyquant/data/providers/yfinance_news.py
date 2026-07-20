"""yfinance news provider: free, keyless, aggregates many publishers.

Each item carries its publisher name, so the sentiment source whitelist does
real work here. Same unofficial-API caveat as our price data; the parser
tolerates missing fields because Yahoo's schema changes without notice.
"""

from datetime import datetime

import yfinance as yf

from diyquant.data.models import NewsItem


def parse_item(raw: dict) -> NewsItem | None:
    content = raw.get("content") or {}
    title = content.get("title")
    pub_date = content.get("pubDate")
    if not title or not pub_date:
        return None
    try:
        ts = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
    except ValueError:
        return None
    return NewsItem(
        ts=ts,
        source=(content.get("provider") or {}).get("displayName", ""),
        headline=title,
        url=(content.get("canonicalUrl") or {}).get("url", ""),
    )


class YFinanceNewsProvider:
    def fetch_news(self, symbol: str, start: datetime) -> list[NewsItem]:
        parsed = (parse_item(raw) for raw in yf.Ticker(symbol).news)
        return [item for item in parsed if item is not None and item.ts >= start]
