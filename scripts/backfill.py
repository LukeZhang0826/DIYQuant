"""Pull daily bars for the configured universe into the local parquet store.

Incremental by default: for a ticker that already has stored bars, only bars newer
than the last stored date are fetched, so the daily run stays cheap at 503-ticker
scale instead of refetching years of history per ticker. Pass --full to force a
complete refetch (e.g. after extending data.start further back).

One bad ticker (delisted, renamed, rate-limited) must not abort the whole run: at
S&P 500 scale some failures are expected, so failures are collected and reported.

Usage: python scripts/backfill.py [--full]
"""

import sys

import pandas as pd

from diyquant.config import get_settings
from diyquant.data.providers.yfinance_provider import YFinanceProvider
from diyquant.data.store import load_bars, save_bars


def _refresh_ticker(
    provider: YFinanceProvider, ticker: str, full_start: str, full: bool
) -> tuple[pd.DataFrame, int | None]:
    """Return (bars, n_new) for one ticker.

    n_new is None for a full fetch, otherwise the count of bars added beyond what was
    already stored (0 means the store was already current).
    """
    existing = None
    if not full:
        try:
            existing = load_bars(ticker)
        except FileNotFoundError:
            existing = None

    if existing is None or existing.empty:
        return provider.fetch_daily_bars(ticker, start=full_start), None

    last = existing.index.max()
    try:
        # Refetch from the last stored day (inclusive) so any late revision to it is
        # picked up; duplicates are dropped on merge.
        new = provider.fetch_daily_bars(ticker, start=last.strftime("%Y-%m-%d"))
    except ValueError:
        return existing, 0  # provider raises on empty: nothing newer, already current

    combined = pd.concat([existing, new])
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    return combined, len(combined) - len(existing)


def main() -> None:
    full = "--full" in sys.argv
    settings = get_settings()
    provider = YFinanceProvider()
    tickers = settings.universe["tickers"]
    failed: list[tuple[str, str]] = []
    for i, ticker in enumerate(tickers, 1):
        try:
            df, n_new = _refresh_ticker(provider, ticker, settings.data.start, full)
            if n_new == 0:
                print(f"[{i}/{len(tickers)}] {ticker}: up to date ({len(df)} bars)")
            else:
                save_bars(ticker, df)
                if n_new is None:
                    print(f"[{i}/{len(tickers)}] {ticker}: {len(df)} bars (full backfill)")
                else:
                    print(f"[{i}/{len(tickers)}] {ticker}: +{n_new} new -> {len(df)} bars")
        except Exception as e:  # noqa: BLE001 - one bad ticker must not abort the run
            failed.append((ticker, str(e)))
            print(f"[{i}/{len(tickers)}] {ticker}: FAILED ({e})")

    mode = "full" if full else "incremental"
    print(f"\ndone ({mode}): {len(tickers) - len(failed)}/{len(tickers)} succeeded")
    if failed:
        print("failed tickers:", ", ".join(t for t, _ in failed))


if __name__ == "__main__":
    main()
