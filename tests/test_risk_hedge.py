import numpy as np
import pandas as pd
import pytest

from diyquant.risk.hedge import DEFAULT_BETA, plan_hedge, rolling_beta


def test_a_name_that_moves_with_the_market_has_beta_one():
    rng = np.random.default_rng(20260808)
    market = pd.Series(rng.normal(0, 0.01, 300))
    beta = rolling_beta(market, market, lookback=120).iloc[-1]
    assert beta == pytest.approx(1.0)


def test_a_name_that_moves_twice_as_hard_has_beta_two():
    rng = np.random.default_rng(20260808)
    market = pd.Series(rng.normal(0, 0.01, 300))
    beta = rolling_beta(market * 2, market, lookback=120).iloc[-1]
    assert beta == pytest.approx(2.0)


def test_beta_is_unknown_until_the_lookback_fills():
    rng = np.random.default_rng(1)
    market = pd.Series(rng.normal(0, 0.01, 200))
    beta = rolling_beta(market, market, lookback=120)
    assert beta.iloc[:118].isna().all()
    assert not np.isnan(beta.iloc[-1])


def test_a_motionless_market_leaves_beta_undefined_not_infinite():
    """Dividing by zero variance must produce NaN, which callers treat as unknown."""
    market = pd.Series([0.0] * 200)
    rng = np.random.default_rng(2)
    symbol = pd.Series(rng.normal(0, 0.01, 200))
    assert (
        rolling_beta(symbol, market, lookback=120).iloc[-1]
        != rolling_beta(symbol, market, lookback=120).iloc[-1]
    )


def test_short_lookback_raises():
    with pytest.raises(ValueError):
        rolling_beta(pd.Series([0.1, 0.2]), pd.Series([0.1, 0.2]), lookback=1)


def test_a_net_long_book_is_hedged_short():
    plan = plan_hedge({"AAA": 0.2, "BBB": 0.2}, {"AAA": 1.0, "BBB": 1.0}, target_beta=0.0)
    assert plan.book_beta == pytest.approx(0.4)
    assert plan.weight == pytest.approx(-0.4)


def test_a_net_short_book_is_hedged_long():
    """The 2026-08-04 shape: four shorts against one long, net short the market."""
    weights = {"TECH": 0.20, "ALB": -0.12, "COHR": -0.06, "SMCI": -0.06, "ON": -0.10}
    betas = {"TECH": 0.9, "ALB": 1.1, "COHR": 1.6, "SMCI": 1.8, "ON": 1.4}
    plan = plan_hedge(weights, betas, target_beta=0.0)
    assert plan.book_beta < 0
    assert plan.weight > 0
    assert plan.book_beta + plan.weight == pytest.approx(0.0)


def test_a_book_already_at_target_trades_no_hedge():
    """A zero-weight hedge costs nothing, which is what makes this safe to run daily."""
    plan = plan_hedge({"AAA": 0.2, "BBB": -0.2}, {"AAA": 1.0, "BBB": 1.0}, target_beta=0.0)
    assert plan.weight == pytest.approx(0.0)


def test_a_non_zero_target_is_reachable():
    plan = plan_hedge({"AAA": 0.5}, {"AAA": 1.0}, target_beta=0.3)
    assert plan.weight == pytest.approx(-0.2)
    assert plan.book_beta + plan.weight == pytest.approx(0.3)


@pytest.mark.parametrize("missing", [None, float("nan")])
def test_unknown_beta_is_assumed_market_like_and_reported(missing):
    """Never 0. Claiming an equity has no market exposure is the least likely value.

    Assuming zero would leave the book under-hedged in exactly the situation
    where the least is known about it.
    """
    betas = {"AAA": 1.0}
    if missing is not None:
        betas["BBB"] = missing
    plan = plan_hedge({"AAA": 0.2, "BBB": 0.2}, betas, target_beta=0.0)
    assert plan.assumed == ("BBB",)
    assert plan.book_beta == pytest.approx(0.2 + 0.2 * DEFAULT_BETA)


def test_flat_positions_are_ignored_entirely():
    plan = plan_hedge({"AAA": 0.2, "GONE": 0.0}, {"AAA": 1.0}, target_beta=0.0)
    assert plan.assumed == ()
    assert plan.weight == pytest.approx(-0.2)
