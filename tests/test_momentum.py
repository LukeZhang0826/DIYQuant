import numpy as np
import pandas as pd
import pytest

from diyquant.signals.technical.momentum import Momentum


def bars(closes) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=len(closes), freq="B")
    return pd.DataFrame({"close": list(closes)}, index=idx)


def test_rising_price_is_long():
    signal = Momentum(lookback=20, skip=5, vol_lookback=5).generate(bars(np.linspace(100, 200, 60)))
    assert signal.iloc[-1] == 1


def test_falling_price_is_short():
    signal = Momentum(lookback=20, skip=5, vol_lookback=5).generate(bars(np.linspace(200, 100, 60)))
    assert signal.iloc[-1] == -1


def test_flat_during_warmup():
    """No position until the full lookback exists, so early bars cannot be traded."""
    signal = Momentum(lookback=20, skip=5, vol_lookback=5).generate(bars(np.linspace(100, 200, 60)))
    assert (signal.iloc[:20] == 0).all()


def test_the_skip_window_is_actually_skipped():
    """A name up for a year then sharply down last month must still read long.

    This is the whole reason 12-1 exists rather than 12-0: the most recent month
    tends to reverse, and a signal that includes it mixes two effects pointing
    opposite ways. An SMA crossover weights those last weeks most heavily and so
    would flip here.
    """
    closes = list(np.linspace(100, 200, 50)) + list(np.linspace(200, 150, 10))
    signal = Momentum(lookback=40, skip=10, vol_lookback=5).generate(bars(closes))
    assert signal.iloc[-1] == 1


def test_strength_prefers_the_steadier_climb():
    """Two names with the same total return rank on how noisily they got there.

    This is the fix for the ranking defect: the plain gap metric would score
    these equally and then let volatility decide, which is how the book ended up
    shorting high-beta names by construction.
    """
    smooth = bars(np.linspace(100, 150, 80))
    jagged_path = np.linspace(100, 150, 80) + np.tile([8.0, -8.0], 40)
    jagged = bars(jagged_path)

    strategy = Momentum(lookback=40, skip=5, vol_lookback=20)
    assert strategy.strength(smooth) > strategy.strength(jagged)


def test_strength_is_never_negative_or_nan():
    strategy = Momentum(lookback=20, skip=5, vol_lookback=5)
    scores = strategy.strength_series(bars(np.linspace(200, 100, 60)))
    assert (scores >= 0).all()
    assert not scores.isna().any()


def test_constant_price_has_no_position():
    """Zero volatility and zero momentum must not become an infinite score."""
    strategy = Momentum(lookback=20, skip=5, vol_lookback=5)
    flat = bars([100.0] * 60)
    assert strategy.generate(flat).iloc[-1] == 0
    assert strategy.strength(flat) == 0.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"lookback": 10, "skip": 10},
        {"lookback": 5, "skip": 10},
        {"lookback": 20, "skip": -1},
        {"lookback": 20, "skip": 5, "vol_lookback": 1},
    ],
)
def test_invalid_parameters_raise(kwargs):
    with pytest.raises(ValueError):
        Momentum(**kwargs)
