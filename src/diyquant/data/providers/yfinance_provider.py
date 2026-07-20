"""yfinance provider — Phase 1 daily bars. auto_adjust=True, so Close is adjusted."""

import pandas as pd
import yfinance as yf


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
