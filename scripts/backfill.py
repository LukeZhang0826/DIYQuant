"""Pull daily bars for the configured universe into the local parquet store.

Usage: python scripts/backfill.py
"""

from diyquant.config import get_settings
from diyquant.data.providers.yfinance_provider import YFinanceProvider
from diyquant.data.store import save_bars


def main() -> None:
    settings = get_settings()
    provider = YFinanceProvider()
    for ticker in settings.universe["tickers"]:
        df = provider.fetch_daily_bars(ticker, start=settings.data.start)
        path = save_bars(ticker, df)
        print(f"{ticker}: {len(df)} bars -> {path}")


if __name__ == "__main__":
    main()
