import pytest

from diyquant.risk.intraday import assess, format_alert, mark_to_market


def test_marks_a_long_and_a_short():
    equity, unpriced = mark_to_market(
        cash=100_000,
        positions={"AAPL": 100, "SPY": -50},
        prices={"AAPL": 200.0, "SPY": 400.0},
    )
    assert equity == 100_000 + 100 * 200 - 50 * 400
    assert unpriced == []


def test_flat_symbols_need_no_price():
    # A zero position is not held, so a missing quote for it is not a problem.
    equity, unpriced = mark_to_market(cash=1_000, positions={"AAPL": 0}, prices={})
    assert equity == 1_000
    assert unpriced == []


@pytest.mark.parametrize("bad", [None, float("nan"), 0.0, -1.0])
def test_unusable_prices_are_reported_not_guessed(bad):
    """The whole safety property: never value a held name at zero.

    Treating a failed quote as 0 reads as a total loss on that position and can
    raise a breach alert off nothing worse than one bad response.
    """
    prices = {"AAPL": 200.0}
    if bad is not None:
        prices["SPY"] = bad
    equity, unpriced = mark_to_market(
        cash=100_000, positions={"AAPL": 100, "SPY": -50}, prices=prices
    )
    assert unpriced == ["SPY"]
    assert equity == 100_000 + 100 * 200  # SPY excluded, not zeroed


def test_quiet_book_neither_warns_nor_breaches():
    mark = assess(anchor_equity=100_000, equity=99_500, max_daily_drawdown_pct=3.0, warn_pct=2.0)
    assert mark.drawdown_pct == pytest.approx(0.5)
    assert not mark.warned
    assert not mark.breached


def test_warns_before_it_breaches():
    mark = assess(anchor_equity=100_000, equity=97_500, max_daily_drawdown_pct=3.0, warn_pct=2.0)
    assert mark.warned
    assert not mark.breached


def test_breach_uses_the_same_limit_as_the_daily_kill_switch():
    mark = assess(anchor_equity=100_000, equity=96_000, max_daily_drawdown_pct=3.0, warn_pct=2.0)
    assert mark.breached and mark.warned
    assert "breaches limit" in mark.reason


def test_a_gain_is_a_negative_drawdown_and_silent():
    mark = assess(anchor_equity=100_000, equity=105_000, max_daily_drawdown_pct=3.0, warn_pct=2.0)
    assert mark.drawdown_pct == pytest.approx(-5.0)
    assert not mark.warned and not mark.breached


def test_the_2026_08_04_book_reproduces():
    """Real numbers from the day that motivated this, marked at the 13:48 low.

    Positions and cash are the recorded post-open book; prices are the actual
    1-minute closes. The flat-cap book breaches, which is the point: nothing
    recorded that it ever happened.
    """
    equity, unpriced = mark_to_market(
        cash=159_024.16,
        positions={"ALB": -169, "COHR": -69, "ORCL": -141, "SMCI": -701, "TECH": 278},
        prices={"ALB": 121.20, "COHR": 334.28, "ORCL": 146.95, "SMCI": 31.55, "TECH": 72.05},
    )
    assert unpriced == []
    mark = assess(anchor_equity=100_515.48, equity=equity, max_daily_drawdown_pct=3.0, warn_pct=2.0)
    assert mark.breached
    assert mark.drawdown_pct > 7.0


def test_alert_says_no_orders_were_placed():
    """The monitor cannot trade, so its message must not read like it did."""
    mark = assess(anchor_equity=100_000, equity=96_000, max_daily_drawdown_pct=3.0, warn_pct=2.0)
    body = format_alert(mark, 100_000, 3.0)
    assert "INTRADAY BREACH" in body
    assert "No orders were placed" in body
