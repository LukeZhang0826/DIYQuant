import numpy as np
import pandas as pd
import pytest

from diyquant.signals.technical.reversal import Reversal


def bars(closes) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=len(closes), freq="B")
    return pd.DataFrame({"close": list(closes)}, index=idx)


def test_a_faller_is_bought():
    """Inverted by design: this is the opposite thesis to momentum."""
    assert (
        Reversal(lookback=5, vol_lookback=5).generate(bars(np.linspace(200, 100, 40))).iloc[-1] == 1
    )


def test_a_riser_is_sold():
    assert (
        Reversal(lookback=5, vol_lookback=5).generate(bars(np.linspace(100, 200, 40))).iloc[-1]
        == -1
    )


def test_opposite_of_momentum_on_the_same_data():
    """The point of including it: the two must genuinely disagree.

    A comparison in which every candidate is a trend follower cannot separate
    "trend following works here" from "this harness flatters trend following".
    """
    from diyquant.signals.technical.momentum import Momentum

    data = bars(np.linspace(100, 200, 80))
    momentum = Momentum(lookback=40, skip=5, vol_lookback=10).generate(data).iloc[-1]
    reversal = Reversal(lookback=5, vol_lookback=10).generate(data).iloc[-1]
    assert momentum == -reversal != 0


def test_flat_during_warmup():
    signal = Reversal(lookback=5, vol_lookback=5).generate(bars(np.linspace(100, 200, 40)))
    assert signal.iloc[0] == 0


def test_constant_price_has_no_position():
    strategy = Reversal(lookback=5, vol_lookback=5)
    flat = bars([100.0] * 40)
    assert strategy.generate(flat).iloc[-1] == 0
    assert strategy.strength(flat) == 0.0


def test_strength_is_never_negative_or_nan():
    scores = Reversal(lookback=5, vol_lookback=5).strength_series(bars(np.linspace(200, 100, 40)))
    assert (scores >= 0).all()
    assert not scores.isna().any()


@pytest.mark.parametrize("kwargs", [{"lookback": 0}, {"lookback": 5, "vol_lookback": 1}])
def test_invalid_parameters_raise(kwargs):
    with pytest.raises(ValueError):
        Reversal(**kwargs)
