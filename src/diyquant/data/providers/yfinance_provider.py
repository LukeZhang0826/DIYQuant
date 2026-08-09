"""yfinance provider: Phase 1 daily bars. auto_adjust=True, so Close is adjusted."""

import pandas as pd
import yfinance as yf


def fetch_last_prices(tickers: list[str]) -> dict[str, float]:
    """Most recent traded price per ticker, for marking a book mid-session.

    Not on the provider protocol yet, and intentionally so: only the intraday
    monitor needs it, and inventing an interface for one caller would fix the
    shape of it before there is a second implementation to test the shape
    against. Promote it when a real second provider needs the same call.

    One batched request rather than a loop over `Ticker.fast_info`: the monitor
    runs on a schedule against a handful of held names, and a per-symbol round
    trip is how a cheap job becomes a slow one. Symbols yfinance will not price
    are simply absent from the result, which `mark_to_market` treats as unpriced
    rather than worthless.
    """
    if not tickers:
        return {}
    frame = yf.download(
        tickers,
        period="1d",
        interval="1m",
        progress=False,
        auto_adjust=True,
        group_by="column",
    )
    if frame is None or frame.empty:
        return {}

    closes = frame["Close"]
    # A single ticker comes back as a plain Series, several as a DataFrame.
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(name=tickers[0])

    prices: dict[str, float] = {}
    for ticker in closes.columns:
        series = closes[ticker].dropna()
        if not series.empty:
            prices[str(ticker)] = float(series.iloc[-1])
    return prices


class YFinanceProvider:
    def fetch_daily_bars(self, ticker: str, start: str) -> pd.DataFrame:
        df = yf.download(ticker, start=start, auto_adjust=True, progress=False)
        if df is None or df.empty:
            raise ValueError(f"No data returned for {ticker} from {start}")
        # yfinance returns MultiIndex columns for single tickers since 0.2.4x
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
        df.index.name = "date"
        return df
