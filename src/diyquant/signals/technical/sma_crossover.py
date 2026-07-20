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
