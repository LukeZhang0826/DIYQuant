from datetime import datetime, timedelta, timezone

import pandas as pd

from diyquant.config import Settings
from diyquant.execution.base import AccountState, FillInfo, OrderResult
from diyquant.execution.ledger import Ledger
from diyquant.execution.pipeline import run_once


class FakeBroker:
    def __init__(self, equity=10_000.0, positions=None, fills=None):
        self.equity = equity
        self.positions = dict(positions or {})
        self.fills = dict(fills or {})
        self.submitted: list[tuple[str, int]] = []

    def get_account(self):
        return AccountState(cash=self.equity, equity=self.equity)

    def get_position(self, symbol):
        return self.positions.get(symbol, 0)

    def submit_market_order(self, symbol, qty):
        self.submitted.append((symbol, qty))
        return OrderResult(broker_order_id=f"o{len(self.submitted)}", status="accepted")

    def get_order_fill(self, broker_order_id):
        return self.fills[broker_order_id]


class ConstantSignal:
    def __init__(self, value: int):
        self.value = value

    def generate(self, bars: pd.DataFrame) -> pd.Series:
        return pd.Series(self.value, index=bars.index)


def make_bars(price: float) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=5, freq="B")
    return pd.DataFrame({"close": [price] * 5}, index=idx)


def make_settings() -> Settings:
    return Settings(
        universe={"tickers": ["AAPL"]},
        data={"provider": "yfinance", "store_path": "data/bars", "start": "2018-01-01"},
        strategy={"name": "sma_crossover", "params": {"fast": 20, "slow": 50}},
        backtest={"cost_bps": 5, "slippage_bps": 2},
        execution={"broker": "alpaca_paper", "ledger_path": "data/ledger.sqlite"},
        sentiment={
            "enabled": False,
            "lookback_hours": 48,
            "half_life_hours": 24,
            "gate_threshold": 0.2,
            "sources": ["benzinga"],
        },
        risk={"max_daily_drawdown_pct": 3.0, "max_position_pct": 20.0},
    )


def hours_ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")


def run(broker, ledger, target=1, price=100.0):
    return run_once(
        broker=broker,
        ledger=ledger,
        bars_by_symbol={"AAPL": make_bars(price)},
        strategy=ConstantSignal(target),
        strategy_name="constant",
        settings=make_settings(),
    )


def test_negative_sentiment_gates_long_entry(tmp_path):
    broker = FakeBroker(equity=10_000)
    ledger = Ledger(tmp_path / "ledger.sqlite")
    report = run_once(
        broker=broker,
        ledger=ledger,
        bars_by_symbol={"AAPL": make_bars(100.0)},
        strategy=ConstantSignal(1),
        strategy_name="constant",
        settings=make_settings(),
        sentiment_scores={"AAPL": -0.8},
    )
    assert broker.submitted == []
    assert report.orders_submitted == 0
    assert any("long gated" in note for note in report.notes)


def test_long_signal_buys_to_cap(tmp_path):
    broker = FakeBroker(equity=10_000)
    ledger = Ledger(tmp_path / "ledger.sqlite")
    report = run(broker, ledger, target=1, price=100.0)
    assert broker.submitted == [("AAPL", 20)]
    assert report.orders_submitted == 1
    assert ledger.pending_orders()[0]["side"] == "buy"


def test_no_order_when_already_at_target(tmp_path):
    broker = FakeBroker(equity=10_000, positions={"AAPL": 20})
    ledger = Ledger(tmp_path / "ledger.sqlite")
    report = run(broker, ledger, target=1, price=100.0)
    assert broker.submitted == []
    assert report.orders_submitted == 0


def test_flat_signal_exits_position(tmp_path):
    broker = FakeBroker(equity=10_000, positions={"AAPL": 20})
    ledger = Ledger(tmp_path / "ledger.sqlite")
    run(broker, ledger, target=0, price=100.0)
    assert broker.submitted == [("AAPL", -20)]


def test_first_run_has_no_drawdown_reference(tmp_path):
    broker = FakeBroker(equity=10_000)
    ledger = Ledger(tmp_path / "ledger.sqlite")
    report = run(broker, ledger, target=1, price=100.0)
    assert not report.halted


def test_kill_switch_halts_and_flattens(tmp_path):
    broker = FakeBroker(equity=9_600, positions={"AAPL": 20})
    ledger = Ledger(tmp_path / "ledger.sqlite")
    ledger.record_equity_snapshot(cash=10_000, equity=10_000)

    report = run(broker, ledger, target=1, price=100.0)

    assert report.halted
    assert ledger.active_halt() is not None
    assert broker.submitted == [("AAPL", -20)]


def test_stale_baseline_skips_drawdown_check(tmp_path):
    """After an outage the old snapshot is not a day-start reference, so do not act on it."""
    broker = FakeBroker(equity=9_000, positions={"AAPL": 20})
    ledger = Ledger(tmp_path / "ledger.sqlite")
    ledger.record_equity_snapshot(cash=10_000, equity=10_000, ts=hours_ago(240))

    report = run(broker, ledger, target=1, price=100.0)

    assert not report.halted
    assert ledger.active_halt() is None
    assert any("drawdown check skipped" in note for note in report.notes)


def test_weekend_gap_baseline_still_trips_kill_switch(tmp_path):
    """A Friday-to-Monday gap is normal cadence, not an outage: the switch must still fire."""
    broker = FakeBroker(equity=9_600, positions={"AAPL": 20})
    ledger = Ledger(tmp_path / "ledger.sqlite")
    ledger.record_equity_snapshot(cash=10_000, equity=10_000, ts=hours_ago(72))

    report = run(broker, ledger, target=1, price=100.0)

    assert report.halted
    assert ledger.active_halt() is not None
    assert broker.submitted == [("AAPL", -20)]


def test_active_halt_blocks_all_trading(tmp_path):
    broker = FakeBroker(equity=10_000)
    ledger = Ledger(tmp_path / "ledger.sqlite")
    ledger.trigger_halt("manual test halt")
    report = run(broker, ledger, target=1, price=100.0)
    assert report.halted
    assert broker.submitted == []


def test_reconciles_pending_fill(tmp_path):
    broker = FakeBroker(
        equity=10_000,
        positions={"AAPL": 20},
        fills={"abc": FillInfo(status="filled", filled_qty=20, avg_price=101.0)},
    )
    ledger = Ledger(tmp_path / "ledger.sqlite")
    order_id = ledger.record_order(
        symbol="AAPL",
        side="buy",
        qty=20,
        signal_name="constant",
        signal_value=1,
        status="submitted",
        broker_order_id="abc",
    )

    report = run(broker, ledger, target=1, price=100.0)

    assert report.fills_reconciled == 1
    assert ledger.pending_orders() == []
    assert ledger.position("AAPL") == 20
    assert order_id not in [row["id"] for row in ledger.pending_orders()]
