"""SMA crossover baseline: long when fast SMA > slow SMA, short when below, flat during warmup."""

import numpy as np
import pandas as pd


class SmaCrossover:
    """Long when the fast average is above the slow one, short when below.

    `rank_by` changes only which candidates win the five funded slots, never
    which names are long or short. See `strength_series`.
    """

    def __init__(
        self, fast: int = 20, slow: int = 50, rank_by: str = "gap", vol_lookback: int = 60
    ):
        if fast >= slow:
            raise ValueError(f"fast ({fast}) must be < slow ({slow})")
        if rank_by not in ("gap", "risk_adjusted"):
            raise ValueError(f"rank_by must be 'gap' or 'risk_adjusted', got {rank_by!r}")
        self.fast = fast
        self.slow = slow
        self.rank_by = rank_by
        self.vol_lookback = vol_lookback

    def generate(self, bars: pd.DataFrame) -> pd.Series:
        close = bars["close"]
        fast_sma = close.rolling(self.fast).mean()
        slow_sma = close.rolling(self.slow).mean()

        # np.sign in one pass rather than three boolean-mask assignments: same
        # result, and this runs 500 symbols per backtest across hundreds of
        # backtests in a walk-forward, where masked __setitem__ dominated the
        # profile. Warmup falls out for free, since the averages are NaN there,
        # NaN propagates through the subtraction, and fillna(0) means flat.
        return np.sign(fast_sma - slow_sma).fillna(0.0).astype(int)

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

        `rank_by="risk_adjusted"` divides that gap by the name's realized
        volatility. The plain gap sorts by how *big* a move was, and the biggest
        moves belong to the most volatile names, which are also the highest-beta
        ones: `docs/baseline.md` measured median beta 1.84 among shorted names
        against 1.38 among longed, which is most of where the book's unwanted
        -0.66 beta came from. Dividing by volatility asks how convincing a trend
        is relative to that name's own noise, a question a calm stock can win.
        Same entries either way, different five funded.
        """
        close = bars["close"]
        fast_sma = close.rolling(self.fast).mean()
        slow_sma = close.rolling(self.slow).mean()
        gap = (fast_sma - slow_sma).abs() / slow_sma.abs()
        if self.rank_by == "risk_adjusted":
            gap = gap / close.pct_change().rolling(self.vol_lookback).std()
        return gap.replace([float("inf"), float("-inf")], 0.0).fillna(0.0)

    def strength(self, bars: pd.DataFrame) -> float:
        """Conviction in the latest target. Defined by the series so the two cannot drift."""
        return float(self.strength_series(bars).iloc[-1])
