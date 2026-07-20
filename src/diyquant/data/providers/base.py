"""Provider interface. Swapping providers is a config change, never a code change."""

from typing import Protocol

import pandas as pd


class BarProvider(Protocol):
    def fetch_daily_bars(self, ticker: str, start: str) -> pd.DataFrame:
        """Return a DataFrame indexed by date with columns: open, high, low, close, volume.

        `close` must be split/dividend-adjusted.
        """
        ...
