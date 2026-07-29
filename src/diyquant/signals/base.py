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


class RankableSignal(Protocol):
    """A Signal that can also say how strongly it believes its latest target."""

    def strength(self, bars: pd.DataFrame) -> float:
        """Non-negative conviction in the latest target, higher being stronger.

        Scale is arbitrary and comparable only within one strategy, since it is
        used to rank symbols against each other, never against a threshold.
        """
        ...


def conviction(strategy: object, bars: pd.DataFrame) -> float:
    """Conviction score for ranking, or 0.0 for a signal that offers none.

    Deliberately optional rather than part of Signal. Ranking only matters when
    there are more signals than capital, and a strategy that does not implement
    it should still be tradable, as every one of them was before selection
    existed. Such a strategy scores flat everywhere, so selection degrades to a
    deterministic cap on how many positions are opened rather than a meaningful
    ordering of them.
    """
    strength = getattr(strategy, "strength", None)
    if strength is None:
        return 0.0
    return float(strength(bars))
