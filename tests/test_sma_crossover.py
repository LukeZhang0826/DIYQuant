import numpy as np
import pandas as pd
import pytest

from diyquant.signals.technical.sma_crossover import SmaCrossover


def make_bars(prices: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="B")
    return pd.DataFrame({"close": prices}, index=idx)


def test_warmup_is_flat():
    bars = make_bars(list(np.linspace(100, 120, 30)))
    signal = SmaCrossover(fast=5, slow=20).generate(bars)
    assert (signal.iloc[:19] == 0).all()


def test_uptrend_goes_long():
    bars = make_bars(list(np.linspace(100, 200, 60)))
    signal = SmaCrossover(fast=5, slow=20).generate(bars)
    assert signal.iloc[-1] == 1


def test_downtrend_goes_short():
    bars = make_bars(list(np.linspace(200, 100, 60)))
    signal = SmaCrossover(fast=5, slow=20).generate(bars)
    assert signal.iloc[-1] == -1


def test_fast_must_be_less_than_slow():
    with pytest.raises(ValueError):
        SmaCrossover(fast=50, slow=20)
