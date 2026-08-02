"""SMA crossover baseline: long when fast SMA > slow SMA, short when below, flat during warmup."""

import pandas as pd


class SmaCrossover:
    def __init__(self, fast: int = 20, slow: int = 50):
        if fast >= slow:
            raise ValueError(f"fast ({fast}) must be < slow ({slow})")
        self.fast = fast
        self.slow = slow

    def generate(self, bars: pd.DataFrame) -> pd.Series:
        close = bars["close"]
        fast_sma = close.rolling(self.fast).mean()
        slow_sma = close.rolling(self.slow).mean()

        signal = pd.Series(0, index=bars.index, dtype=int)
        signal[fast_sma > slow_sma] = 1
        signal[fast_sma < slow_sma] = -1
        # Warmup period: no position until slow SMA exists
        signal[slow_sma.isna()] = 0
        return signal

    def strength_series(self, bars: pd.DataFrame) -> pd.Series:
        """Conviction at every bar: how far apart the two averages are.

        The crossover is all sign and no magnitude, which is fine across four
        tickers and useless across five hundred, where nearly everything is in
        some active state and only a few can be funded. The gap is the natural
        magnitude the signal already computes and throws away.

        Normalised by the slow average so it reads as a percentage, which makes
        a $400 stock and a $40 one comparable. Absolute value, because a strong
        short deserves a slot as much as a strong long. 0.0 during warmup, which
        ranks last without special-casing.

        The series exists for backtesting. Live only ever needs the last value,
        but asking for it one bar at a time across a history makes ranking
        quadratic, and this computation is already vectorised.
        """
        close = bars["close"]
        fast_sma = close.rolling(self.fast).mean()
        slow_sma = close.rolling(self.slow).mean()
        gap = (fast_sma - slow_sma).abs() / slow_sma.abs()
        return gap.replace([float("inf"), float("-inf")], 0.0).fillna(0.0)

    def strength(self, bars: pd.DataFrame) -> float:
        """Conviction in the latest target. Defined by the series so the two cannot drift."""
        return float(self.strength_series(bars).iloc[-1])
