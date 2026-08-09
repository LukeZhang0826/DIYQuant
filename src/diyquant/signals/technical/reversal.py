"""Short-term reversal: buy the past week's losers, sell its winners.

Included as a genuine alternative rather than a variation. Momentum and the SMA
crossover are both trend-following and will tend to be right and wrong on the
same days; reversal is the documented anomaly that points the other way at short
horizons (Lehmann 1990, Jegadeesh 1990), so it tests whether the pipeline's
selection and sizing machinery carries any edge at all when the underlying
thesis is inverted.

That makes it useful as evidence even if it loses. A comparison where every
candidate is a trend follower cannot distinguish "trend following works here"
from "this harness flatters trend following".

The honest caveat, stated up front because it will not show up in the walk-forward
numbers: reversal trades far more often than a 12-month signal, and this project
charges 5bps cost plus 2bps slippage per side. The `zero costs` ablation row put
all transaction costs at only ~21pp for the SMA baseline, but that strategy turns
over slowly. Read the reversal row against its own turnover, not the baseline's.
"""

import pandas as pd


class Reversal:
    def __init__(self, lookback: int = 5, vol_lookback: int = 60):
        if lookback < 1:
            raise ValueError(f"lookback must be at least 1, got {lookback}")
        if vol_lookback < 2:
            raise ValueError(f"vol_lookback must be at least 2, got {vol_lookback}")
        self.lookback = lookback
        self.vol_lookback = vol_lookback

    def _recent_return(self, close: pd.Series) -> pd.Series:
        return close / close.shift(self.lookback) - 1.0

    def generate(self, bars: pd.DataFrame) -> pd.Series:
        recent = self._recent_return(bars["close"])
        signal = pd.Series(0, index=bars.index, dtype=int)
        # Inverted on purpose: a name that fell is a buy.
        signal[recent < 0] = 1
        signal[recent > 0] = -1
        signal[recent.isna()] = 0
        return signal

    def strength_series(self, bars: pd.DataFrame) -> pd.Series:
        """How far the name moved relative to its own noise. Big dislocations rank first."""
        close = bars["close"]
        move = self._recent_return(close).abs()
        vol = close.pct_change().rolling(self.vol_lookback).std()
        score = move / vol
        return score.replace([float("inf"), float("-inf")], 0.0).fillna(0.0)

    def strength(self, bars: pd.DataFrame) -> float:
        return float(self.strength_series(bars).iloc[-1])
