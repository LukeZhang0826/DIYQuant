import numpy as np
import pandas as pd
import pytest

from diyquant.risk.sizing import realized_vol_pct, target_shares, volatility_budget_pct


def test_long_sizes_to_cap():
    assert target_shares(target=1, equity=10_000, price=100, max_position_pct=20.0) == 20


def test_short_sizes_to_cap_negative():
    assert target_shares(target=-1, equity=10_000, price=100, max_position_pct=20.0) == -20


def test_flat_target_is_zero_shares():
    assert target_shares(target=0, equity=10_000, price=100, max_position_pct=20.0) == 0


def test_rounds_down_to_whole_shares():
    # budget 2000, price 333 -> 6.006 shares -> 6
    assert target_shares(target=1, equity=10_000, price=333, max_position_pct=20.0) == 6


def test_zero_shares_when_one_share_breaches_cap():
    # budget 2000, price 2500 -> 0 shares rather than breaching the cap
    assert target_shares(target=1, equity=10_000, price=2_500, max_position_pct=20.0) == 0


def test_invalid_target_raises():
    with pytest.raises(ValueError):
        target_shares(target=2, equity=10_000, price=100, max_position_pct=20.0)


def test_non_positive_equity_raises():
    with pytest.raises(ValueError):
        target_shares(target=1, equity=0, price=100, max_position_pct=20.0)


def test_non_positive_price_raises():
    with pytest.raises(ValueError):
        target_shares(target=1, equity=10_000, price=0, max_position_pct=20.0)


def test_vol_budget_hits_the_cap_at_the_reference_volatility():
    # 0.4% of equity per 1-sigma day, on a 2%/day name, is exactly 20% of equity
    assert volatility_budget_pct(2.0, target_risk_pct=0.4, max_position_pct=20.0) == 20.0


def test_vol_budget_shrinks_a_jumpy_name():
    # COHR territory: 6%/day earns a third of the flat cap, not the whole thing
    assert volatility_budget_pct(6.0, target_risk_pct=0.4, max_position_pct=20.0) == pytest.approx(
        6.667, abs=1e-3
    )


def test_vol_budget_never_exceeds_the_flat_cap():
    # A calm name would be allowed 200% of equity on risk grounds alone; the cap
    # is a hard backstop, so scaling can only ever de-risk.
    assert volatility_budget_pct(0.2, target_risk_pct=0.4, max_position_pct=20.0) == 20.0


def test_vol_budget_disabled_returns_the_flat_cap():
    assert volatility_budget_pct(6.0, target_risk_pct=0.0, max_position_pct=20.0) == 20.0


def test_unknown_volatility_gets_no_position():
    # The whole point: a name we cannot size must not default to the largest
    # allowed position just because its history is too short to measure.
    assert volatility_budget_pct(float("nan"), target_risk_pct=0.4, max_position_pct=20.0) == 0.0


def test_zero_volatility_gets_the_cap():
    # Distinct from unknown: a price that does not move cannot breach a budget.
    assert volatility_budget_pct(0.0, target_risk_pct=0.4, max_position_pct=20.0) == 20.0


def test_realized_vol_is_nan_until_the_lookback_fills():
    close = pd.Series(np.linspace(100, 110, 10))
    vol = realized_vol_pct(close, lookback=5)
    assert vol.iloc[:4].isna().all()
    assert not np.isnan(vol.iloc[-1])


def test_realized_vol_is_a_percentage():
    # Alternating +10%/-10% moves: standard deviation of returns is ~0.1, so the
    # function must report ~10, not ~0.1.
    close = pd.Series([100, 110, 99, 108.9, 98.01, 107.811, 97.03])
    assert realized_vol_pct(close, lookback=6).iloc[-1] == pytest.approx(10.5, abs=0.5)
