"""Local parquet store for historical bars. One file per ticker."""

from pathlib import Path

import pandas as pd

from diyquant.config import PROJECT_ROOT, get_settings


def _bar_path(ticker: str) -> Path:
    store = PROJECT_ROOT / get_settings().data.store_path
    store.mkdir(parents=True, exist_ok=True)
    return store / f"{ticker.upper()}.parquet"


def save_bars(ticker: str, df: pd.DataFrame) -> Path:
    path = _bar_path(ticker)
    df.to_parquet(path)
    return path


def load_bars(ticker: str) -> pd.DataFrame:
    path = _bar_path(ticker)
    if not path.exists():
        raise FileNotFoundError(f"No stored bars for {ticker}. Run scripts/backfill.py first.")
    return pd.read_parquet(path)
