"""Cross-sectional momentum: buy what has been rising, sell what has been falling.

The oldest and most replicated anomaly in equities (Jegadeesh & Titman, 1993).
It is picked here for that prior evidence rather than because it scored well in
this repo's harness, which is the order those two things have to come in.

Two differences from the SMA crossover that matter:

**It skips the most recent month.** The classic 12-1 form measures the return
from twelve months ago to one month ago. The skip exists because the most recent
month tends to *reverse*, so including it mixes two effects that point opposite
ways and blunts both. `SmaCrossover` weights the last few weeks most heavily and
so eats that reversal head-on.

**It ranks on a risk-adjusted score, not raw magnitude.** This is the direct fix
for the defect measured in `docs/baseline.md`: ranking on `|fast - slow| / slow`
sorts by how *big* a move was, and the biggest moves belong to the most volatile
names, which are also the highest-beta ones. Measured on the baseline config, the
median beta of shorted names was 1.84 against 1.38 for longed, which is where the
book's unwanted -0.66 beta came from. Dividing by realized volatility asks "how
convincing is this trend relative to the noise in this name", which a calm stock
can win, so the ranking stops being a beta sort wearing a trend costume.

Volatility is recomputed here rather than imported from `risk.sizing`: a signal
must stay a pure function of its own bars, and the two lookbacks answer different
questions and should be free to differ.
"""

import pandas as pd


class Momentum:
    def __init__(self, lookback: int = 252, skip: int = 21, vol_lookback: int = 60):
        if lookback <= skip:
            raise ValueError(f"lookback ({lookback}) must exceed skip ({skip})")
        if skip < 0:
            raise ValueError(f"skip must not be negative, got {skip}")
        if vol_lookback < 2:
            raise ValueError(f"vol_lookback must be at least 2, got {vol_lookback}")
        self.lookback = lookback
        self.skip = skip
        self.vol_lookback = vol_lookback

    def _momentum(self, close: pd.Series) -> pd.Series:
        """Total return from `lookback` bars ago to `skip` bars ago."""
        recent = close.shift(self.skip)
        older = close.shift(self.lookback)
        return recent / older - 1.0

    def generate(self, bars: pd.DataFrame) -> pd.Series:
        momentum = self._momentum(bars["close"])
        signal = pd.Series(0, index=bars.index, dtype=int)
        signal[momentum > 0] = 1
        signal[momentum < 0] = -1
        # Warmup: no position until the full lookback exists. NaN comparisons are
        # already False above, so this is belt and braces on an explicit rule.
        signal[momentum.isna()] = 0
        return signal

    def strength_series(self, bars: pd.DataFrame) -> pd.Series:
        """Momentum per unit of the name's own volatility. Non-negative, 0 during warmup."""
        close = bars["close"]
        momentum = self._momentum(close).abs()
        vol = close.pct_change().rolling(self.vol_lookback).std()
        score = momentum / vol
        return score.replace([float("inf"), float("-inf")], 0.0).fillna(0.0)

    def strength(self, bars: pd.DataFrame) -> float:
        return float(self.strength_series(bars).iloc[-1])
