import numpy as np
import pandas as pd
import pytest

from diyquant.backtest.engine import run_backtest


def make_bars(prices: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="B")
    return pd.DataFrame({"close": prices}, index=idx)


def test_flat_signal_earns_nothing_and_pays_nothing():
    bars = make_bars(list(np.linspace(100, 150, 50)))
    signal = pd.Series(0, index=bars.index)
    result = run_backtest(bars, signal)
    assert result.total_return == 0.0
    assert result.n_trades == 0


def test_always_long_matches_benchmark_minus_entry_cost():
    bars = make_bars(list(np.linspace(100, 150, 50)))
    signal = pd.Series(1, index=bars.index)
    result = run_backtest(bars, signal, cost_bps=0, slippage_bps=0)
    # With zero costs, always-long (from bar 2 on) tracks buy-and-hold from bar 2 on
    assert result.total_return == pytest.approx(result.benchmark_return, rel=1e-9)


def test_costs_reduce_returns():
    bars = make_bars(list(np.linspace(100, 150, 50)))
    signal = pd.Series(1, index=bars.index)
    free = run_backtest(bars, signal, cost_bps=0, slippage_bps=0)
    costly = run_backtest(bars, signal, cost_bps=50, slippage_bps=10)
    assert costly.total_return < free.total_return
