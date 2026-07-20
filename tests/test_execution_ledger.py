from diyquant.execution.ledger import Ledger


def make_ledger(tmp_path):
    return Ledger(tmp_path / "ledger.sqlite")


def test_order_lifecycle_submitted_to_filled(tmp_path):
    ledger = make_ledger(tmp_path)
    order_id = ledger.record_order(
        symbol="AAPL",
        side="buy",
        qty=20,
        signal_name="sma_crossover",
        signal_value=1,
        status="submitted",
        broker_order_id="abc",
    )
    assert [row["id"] for row in ledger.pending_orders()] == [order_id]

    ledger.update_order_status(order_id, "filled")
    assert ledger.pending_orders() == []


def test_position_is_net_of_fills(tmp_path):
    ledger = make_ledger(tmp_path)
    ledger.record_fill(order_id=1, symbol="AAPL", side="buy", qty=20, price=100.0)
    ledger.record_fill(order_id=2, symbol="AAPL", side="sell", qty=5, price=110.0)
    ledger.record_fill(order_id=3, symbol="MSFT", side="buy", qty=3, price=400.0)
    assert ledger.position("AAPL") == 15
    assert ledger.position("MSFT") == 3
    assert ledger.position("NVDA") == 0


def test_last_equity_returns_latest_snapshot(tmp_path):
    ledger = make_ledger(tmp_path)
    assert ledger.last_equity() is None
    ledger.record_equity_snapshot(cash=5_000, equity=10_000)
    ledger.record_equity_snapshot(cash=4_000, equity=10_500)
    assert ledger.last_equity() == 10_500


def test_halt_lifecycle(tmp_path):
    ledger = make_ledger(tmp_path)
    assert ledger.active_halt() is None
    halt_id = ledger.trigger_halt("daily drawdown 4.00% breaches limit 3.00%")
    assert ledger.active_halt()["id"] == halt_id
    ledger.clear_halt(halt_id)
    assert ledger.active_halt() is None
