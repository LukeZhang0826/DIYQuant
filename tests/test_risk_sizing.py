import pytest

from diyquant.risk.sizing import target_shares


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
