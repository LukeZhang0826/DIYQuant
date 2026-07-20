import pytest

from diyquant.risk.limits import check_daily_drawdown, check_position_cap


def test_small_loss_is_allowed():
    decision = check_daily_drawdown(
        day_start_equity=10_000, current_equity=9_900, max_daily_drawdown_pct=3.0
    )
    assert decision.allowed


def test_gain_is_allowed():
    decision = check_daily_drawdown(
        day_start_equity=10_000, current_equity=10_500, max_daily_drawdown_pct=3.0
    )
    assert decision.allowed


def test_loss_at_limit_trips_kill_switch():
    decision = check_daily_drawdown(
        day_start_equity=10_000, current_equity=9_700, max_daily_drawdown_pct=3.0
    )
    assert not decision.allowed
    assert "3.00%" in decision.reason


def test_loss_beyond_limit_trips_kill_switch():
    decision = check_daily_drawdown(
        day_start_equity=10_000, current_equity=9_000, max_daily_drawdown_pct=3.0
    )
    assert not decision.allowed


def test_drawdown_requires_positive_day_start_equity():
    with pytest.raises(ValueError):
        check_daily_drawdown(day_start_equity=0, current_equity=0, max_daily_drawdown_pct=3.0)


def test_position_under_cap_is_allowed():
    decision = check_position_cap(position_value=1_500, equity=10_000, max_position_pct=20.0)
    assert decision.allowed


def test_position_exactly_at_cap_is_allowed():
    decision = check_position_cap(position_value=2_000, equity=10_000, max_position_pct=20.0)
    assert decision.allowed


def test_position_over_cap_is_blocked():
    decision = check_position_cap(position_value=2_500, equity=10_000, max_position_pct=20.0)
    assert not decision.allowed
    assert "cap" in decision.reason


def test_short_position_counts_by_absolute_value():
    decision = check_position_cap(position_value=-2_500, equity=10_000, max_position_pct=20.0)
    assert not decision.allowed


def test_position_cap_requires_positive_equity():
    with pytest.raises(ValueError):
        check_position_cap(position_value=100, equity=0, max_position_pct=20.0)
