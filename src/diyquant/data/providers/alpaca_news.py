"""Alpaca historical news provider (Benzinga feed).

Uses the same paper API keys as the broker. Returns plain NewsItem records so
nothing downstream depends on the Alpaca SDK types.
"""

from datetime import datetime

from alpaca.data.historical.news import NewsClient
from alpaca.data.requests import NewsRequest

from diyquant.data.models import NewsItem


class AlpacaNewsProvider:
    def __init__(self, api_key: str, secret_key: str):
        if not api_key or not secret_key:
            raise ValueError("Alpaca keys missing: set ALPACA_API_KEY / ALPACA_SECRET_KEY in .env")
        self._client = NewsClient(api_key, secret_key)

    def fetch_news(self, symbol: str, start: datetime) -> list[NewsItem]:
        news = self._client.get_news(NewsRequest(symbols=symbol, start=start))
        return [
            NewsItem(
                ts=item.created_at,
                source=(item.source or ""),
                headline=item.headline,
                url=(item.url or ""),
            )
            for item in news.data["news"]
        ]
