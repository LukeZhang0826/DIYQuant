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

    def strength(self, bars: pd.DataFrame) -> float:
        """Conviction in the latest target: how far apart the two averages are.

        The crossover is all sign and no magnitude, which is fine across four
        tickers and useless across five hundred, where nearly everything is in
        some active state and only a few can be funded. The gap is the natural
        magnitude the signal already computes and throws away.

        Normalised by the slow average so it reads as a percentage, which makes
        a $400 stock and a $40 one comparable. Absolute value, because a strong
        short deserves a slot as much as a strong long. Returns 0.0 during
        warmup, which ranks last without special-casing.
        """
        close = bars["close"]
        fast_sma = close.rolling(self.fast).mean().iloc[-1]
        slow_sma = close.rolling(self.slow).mean().iloc[-1]
        if pd.isna(fast_sma) or pd.isna(slow_sma) or slow_sma == 0:
            return 0.0
        return abs(float(fast_sma) - float(slow_sma)) / abs(float(slow_sma))
