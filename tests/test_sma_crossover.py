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


def test_strength_is_zero_during_warmup():
    bars = make_bars(list(np.linspace(100, 120, 10)))
    assert SmaCrossover(fast=5, slow=20).strength(bars) == 0.0


def test_strength_grows_with_the_gap_between_the_averages():
    steep = make_bars(list(np.linspace(100, 300, 60)))
    shallow = make_bars(list(np.linspace(100, 105, 60)))
    strategy = SmaCrossover(fast=5, slow=20)
    assert strategy.strength(steep) > strategy.strength(shallow)


def test_strength_is_positive_for_a_downtrend():
    """A strong short deserves a slot as much as a strong long."""
    bars = make_bars(list(np.linspace(200, 100, 60)))
    assert SmaCrossover(fast=5, slow=20).strength(bars) > 0


def test_strength_is_scale_free():
    """A $400 stock and a $40 one must be comparable, or price picks the book."""
    cheap = make_bars(list(np.linspace(10, 20, 60)))
    dear = make_bars(list(np.linspace(100, 200, 60)))
    strategy = SmaCrossover(fast=5, slow=20)
    assert strategy.strength(cheap) == pytest.approx(strategy.strength(dear))


def test_flat_prices_have_no_conviction():
    bars = make_bars([100.0] * 60)
    assert SmaCrossover(fast=5, slow=20).strength(bars) == pytest.approx(0.0)
