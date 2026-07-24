import pandas as pd

from diyquant.execution.sim_broker import SimulatedBroker

COST_BPS = 5.0
SLIP_BPS = 2.0


def make_bars(n_days: int) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n_days, freq="B")
    prices = [100.0 + i for i in range(n_days)]
    return pd.DataFrame({"open": prices, "close": prices}, index=idx)


def make_broker(tmp_path, n_days: int) -> SimulatedBroker:
    return SimulatedBroker(
        tmp_path / "sim.sqlite",
        {"AAPL": make_bars(n_days)},
        cost_bps=COST_BPS,
        slippage_bps=SLIP_BPS,
        starting_cash=100_000.0,
    )


def test_starting_account_state(tmp_path):
    broker = make_broker(tmp_path, 5)
    account = broker.get_account()
    assert account.cash == 100_000.0
    assert account.equity == 100_000.0
    assert broker.get_position("AAPL") == 0


def test_order_pends_until_next_bar_exists(tmp_path):
    broker = make_broker(tmp_path, 5)
    result = broker.submit_market_order("AAPL", 20)
    fill = broker.get_order_fill(result.broker_order_id)
    assert fill.status == "accepted"
    assert broker.get_position("AAPL") == 0


def test_order_fills_at_next_open_with_slippage(tmp_path):
    broker = make_broker(tmp_path, 5)
    result = broker.submit_market_order("AAPL", 20)
    broker.close()

    # Next run: one more trading day of data exists (open = 105.0)
    broker2 = make_broker(tmp_path, 6)
    fill = broker2.get_order_fill(result.broker_order_id)

    expected_price = 105.0 * (1 + SLIP_BPS / 10_000)
    assert fill.status == "filled"
    assert fill.filled_qty == 20
    assert abs(fill.avg_price - expected_price) < 1e-9
    assert broker2.get_position("AAPL") == 20

    fees = 20 * expected_price * COST_BPS / 10_000
    expected_cash = 100_000.0 - 20 * expected_price - fees
    assert abs(broker2.get_account().cash - expected_cash) < 1e-9


def test_fill_is_idempotent(tmp_path):
    broker = make_broker(tmp_path, 5)
    result = broker.submit_market_order("AAPL", 20)
    broker.close()

    broker2 = make_broker(tmp_path, 6)
    first = broker2.get_order_fill(result.broker_order_id)
    second = broker2.get_order_fill(result.broker_order_id)
    assert first == second
    assert broker2.get_position("AAPL") == 20  # not 40


def test_sell_receives_slippage_against_and_flattens(tmp_path):
    broker = make_broker(tmp_path, 5)
    buy = broker.submit_market_order("AAPL", 20)
    broker.close()

    broker2 = make_broker(tmp_path, 6)
    broker2.get_order_fill(buy.broker_order_id)
    sell = broker2.submit_market_order("AAPL", -20)
    broker2.close()

    broker3 = make_broker(tmp_path, 7)
    fill = broker3.get_order_fill(sell.broker_order_id)
    assert fill.status == "filled"
    assert abs(fill.avg_price - 106.0 * (1 - SLIP_BPS / 10_000)) < 1e-9
    assert broker3.get_position("AAPL") == 0


def test_order_pends_when_symbol_bars_are_missing(tmp_path):
    """A ticker whose bars are no longer loaded (delisted, or dropped from the
    universe) must not crash reconciliation; its order stays pending."""
    broker = make_broker(tmp_path, 5)
    result = broker.submit_market_order("AAPL", 20)
    broker.close()

    # Next run: AAPL cannot be priced, so it is absent from the bars dict.
    broker2 = SimulatedBroker(
        tmp_path / "sim.sqlite",
        {},
        cost_bps=COST_BPS,
        slippage_bps=SLIP_BPS,
        starting_cash=100_000.0,
    )
    fill = broker2.get_order_fill(result.broker_order_id)
    assert fill.status == "accepted"
    assert fill.filled_qty == 0


def test_equity_marks_positions_to_latest_close(tmp_path):
    broker = make_broker(tmp_path, 5)
    result = broker.submit_market_order("AAPL", 20)
    broker.close()

    broker2 = make_broker(tmp_path, 6)
    broker2.get_order_fill(result.broker_order_id)
    account = broker2.get_account()
    assert abs(account.equity - (account.cash + 20 * 105.0)) < 1e-9
