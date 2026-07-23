"""Pull daily bars for the configured universe into the local parquet store.

One bad ticker (delisted, renamed, rate-limited) must not abort the whole run: at S&P
500 scale some failures are expected, so failures are collected and reported, not raised.

Usage: python scripts/backfill.py
"""

from diyquant.config import get_settings
from diyquant.data.providers.yfinance_provider import YFinanceProvider
from diyquant.data.store import save_bars


def main() -> None:
    settings = get_settings()
    provider = YFinanceProvider()
    tickers = settings.universe["tickers"]
    failed: list[tuple[str, str]] = []
    for i, ticker in enumerate(tickers, 1):
        try:
            df = provider.fetch_daily_bars(ticker, start=settings.data.start)
            path = save_bars(ticker, df)
            print(f"[{i}/{len(tickers)}] {ticker}: {len(df)} bars -> {path}")
        except Exception as e:  # noqa: BLE001 - one bad ticker must not abort the run
            failed.append((ticker, str(e)))
            print(f"[{i}/{len(tickers)}] {ticker}: FAILED ({e})")

    print(f"\ndone: {len(tickers) - len(failed)}/{len(tickers)} succeeded")
    if failed:
        print("failed tickers:", ", ".join(t for t, _ in failed))


if __name__ == "__main__":
    main()
