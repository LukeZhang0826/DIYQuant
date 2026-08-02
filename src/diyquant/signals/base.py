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


def conviction_series(strategy: object, bars: pd.DataFrame) -> pd.Series:
    """Conviction at every bar, or a flat zero series for a strategy offering none.

    Same optional contract as `conviction`, in the shape a backtest needs. Asking
    a strategy for its latest conviction once per historical bar would re-derive
    the whole rolling computation every time, so ranking a 500-name universe
    across years is only tractable if the strategy can hand over the series it
    already computes internally.
    """
    series = getattr(strategy, "strength_series", None)
    if series is None:
        return pd.Series(0.0, index=bars.index)
    return series(bars).astype(float)
