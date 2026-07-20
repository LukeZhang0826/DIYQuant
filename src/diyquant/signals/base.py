"""Signal contract: pure function of bars -> target position series in {-1, 0, +1}.

No API calls, no state, no side effects. This is what makes backtest/live parity provable.
"""

from typing import Protocol

import pandas as pd


class Signal(Protocol):
    def generate(self, bars: pd.DataFrame) -> pd.Series:
        """Return a Series aligned to bars.index with values in {-1, 0, 1}.

        The value at index T is the position computed FROM bar T's data.
        Execution timing (T+1) is the backtester's/executor's responsibility.
        """
        ...
