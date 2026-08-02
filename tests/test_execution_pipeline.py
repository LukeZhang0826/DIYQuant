from datetime import datetime, timedelta, timezone

import pandas as pd

from diyquant.config import Settings
from diyquant.execution.base import AccountState, FillInfo, OrderResult
from diyquant.execution.ledger import Ledger
from diyquant.execution.pipeline import run_once
from diyquant.execution.sim_broker import SimulatedBroker


class FakeBroker:
    def __init__(self, equity=10_000.0, positions=None, fills=None):
        self.equity = equity
        self.positions = dict(positions or {})
        self.fills = dict(fills or {})
        self.submitted: list[tuple[str, int]] = []
        self.cancelled: list[str] = []

    def get_account(self):
        return AccountState(cash=self.equity, equity=self.equity)

    def get_position(self, symbol):
        return self.positions.get(symbol, 0)

    def submit_market_order(self, symbol, qty):
        self.submitted.append((symbol, qty))
        return OrderResult(broker_order_id=f"o{len(self.submitted)}", status="accepted")

    def get_order_fill(self, broker_order_id):
        return self.fills[broker_order_id]

    def cancel_order(self, broker_order_id):
        self.cancelled.append(broker_order_id)


class ConstantSignal:
    def __init__(self, value: int):
        self.value = value

    def generate(self, bars: pd.DataFrame) -> pd.Series:
        return pd.Series(self.value, index=bars.index)


def make_bars(price: float) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=5, freq="B")
    return pd.DataFrame({"close": [price] * 5}, index=idx)


def make_settings(**risk_overrides) -> Settings:
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
        risk={"max_daily_drawdown_pct": 3.0, "max_position_pct": 20.0, **risk_overrides},
    )


class PricedConviction:
    """Constant target, conviction equal to the last close, so tests rank by price."""

    def __init__(self, value: int):
        self.value = value

    def generate(self, bars: pd.DataFrame) -> pd.Series:
        return pd.Series(self.value, index=bars.index)

    def strength(self, bars: pd.DataFrame) -> float:
        return float(bars["close"].iloc[-1])


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


def test_gate_veto_is_recorded_with_the_signal_it_overrode(tmp_path):
    """A veto is only interpretable next to what the base signal wanted."""
    ledger = Ledger(tmp_path / "ledger.sqlite")
    run_once(
        broker=FakeBroker(equity=10_000),
        ledger=ledger,
        bars_by_symbol={"AAPL": make_bars(100.0)},
        strategy=ConstantSignal(1),
        strategy_name="constant",
        settings=make_settings(),
        sentiment_scores={"AAPL": -0.8},
    )
    (row,) = ledger.sentiment_gates()
    assert row["symbol"] == "AAPL"
    assert row["raw_signal"] == 1
    assert row["gated_signal"] == 0
    assert row["vetoed"] == 1
    assert row["score"] == -0.8
    assert "long gated" in row["reason"]


def test_gate_records_evaluations_it_did_not_veto(tmp_path):
    """Without the non-vetoes there is no denominator, so no way to judge the gate."""
    ledger = Ledger(tmp_path / "ledger.sqlite")
    run_once(
        broker=FakeBroker(equity=10_000),
        ledger=ledger,
        bars_by_symbol={"AAPL": make_bars(100.0)},
        strategy=ConstantSignal(1),
        strategy_name="constant",
        settings=make_settings(),
        sentiment_scores={"AAPL": 0.5},
    )
    (row,) = ledger.sentiment_gates()
    assert row["vetoed"] == 0
    assert row["raw_signal"] == row["gated_signal"] == 1
    assert row["reason"] == ""


def test_absent_news_is_recorded_as_null_not_zero(tmp_path):
    """No news is not neutral news; conflating them would corrupt later analysis."""
    ledger = Ledger(tmp_path / "ledger.sqlite")
    run_once(
        broker=FakeBroker(equity=10_000),
        ledger=ledger,
        bars_by_symbol={"AAPL": make_bars(100.0)},
        strategy=ConstantSignal(1),
        strategy_name="constant",
        settings=make_settings(),
        sentiment_scores={"AAPL": None},
    )
    (row,) = ledger.sentiment_gates()
    assert row["score"] is None
    assert row["vetoed"] == 0


def test_nothing_recorded_when_sentiment_is_disabled(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    run(FakeBroker(equity=10_000), ledger, target=1, price=100.0)
    assert ledger.sentiment_gates() == []


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


def test_untradable_symbol_winds_down_but_is_not_traded(tmp_path):
    """A ticker that left the universe must still fill its open order (wind-down),
    but must not receive a fresh signal-driven trade."""
    broker = FakeBroker(
        equity=10_000,
        positions={"SPY": 26},
        fills={"sim-6": FillInfo(status="filled", filled_qty=26, avg_price=500.0)},
    )
    ledger = Ledger(tmp_path / "ledger.sqlite")
    ledger.record_order(
        symbol="SPY",
        side="sell",
        qty=26,
        signal_name="constant",
        signal_value=0,
        status="submitted",
        broker_order_id="sim-6",
    )

    report = run_once(
        broker=broker,
        ledger=ledger,
        bars_by_symbol={"AAPL": make_bars(100.0), "SPY": make_bars(500.0)},
        strategy=ConstantSignal(1),
        strategy_name="constant",
        settings=make_settings(),
        tradable={"AAPL"},
    )

    # SPY's open order still reconciled, but only AAPL got a new order.
    assert report.fills_reconciled == 1
    assert broker.submitted == [("AAPL", 20)]
    # SPY is closed out; the only order left pending is AAPL's fresh buy.
    assert [row["symbol"] for row in ledger.pending_orders()] == ["AAPL"]


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


def priced(symbols: dict[str, float]) -> dict[str, pd.DataFrame]:
    return {sym: make_bars(price) for sym, price in symbols.items()}


def test_five_hundred_live_signals_fund_only_max_positions(tmp_path):
    """The bug: ~500 names carry a signal, capital funds five, iteration order decided which."""
    broker = FakeBroker(equity=100_000)
    ledger = Ledger(tmp_path / "ledger.sqlite")

    report = run_once(
        broker=broker,
        ledger=ledger,
        bars_by_symbol=priced({f"S{i:03d}": 100.0 for i in range(500)}),
        strategy=ConstantSignal(1),
        strategy_name="constant",
        settings=make_settings(),
    )

    assert report.candidates == 500
    assert report.selected == 5
    assert len(broker.submitted) == 5
    assert report.orders_submitted == 5


def test_the_strongest_conviction_gets_funded(tmp_path):
    broker = FakeBroker(equity=100_000)
    ledger = Ledger(tmp_path / "ledger.sqlite")

    run_once(
        broker=broker,
        ledger=ledger,
        bars_by_symbol=priced({"A": 60.0, "B": 50.0, "C": 40.0, "D": 30.0}),
        strategy=PricedConviction(1),
        strategy_name="priced",
        settings=make_settings(max_positions=2),
    )

    assert sorted(sym for sym, _ in broker.submitted) == ["A", "B"]


def test_a_holding_that_loses_its_slot_is_wound_down(tmp_path):
    """Missing selection means flat, not "leave it alone"."""
    broker = FakeBroker(equity=100_000, positions={"C": 500})
    ledger = Ledger(tmp_path / "ledger.sqlite")

    run_once(
        broker=broker,
        ledger=ledger,
        bars_by_symbol=priced({"A": 60.0, "B": 50.0, "C": 40.0}),
        strategy=PricedConviction(1),
        strategy_name="priced",
        settings=make_settings(max_positions=1, hysteresis_rank=1),
    )

    assert ("C", -500) in broker.submitted


def test_hysteresis_keeps_a_holding_that_slipped_one_place(tmp_path):
    """F ranks 6th of 6 but is held, so it keeps its slot instead of churning."""
    held_shares = int(100_000 * 0.20 / 10.0)
    broker = FakeBroker(equity=100_000, positions={"F": held_shares})
    ledger = Ledger(tmp_path / "ledger.sqlite")

    report = run_once(
        broker=broker,
        ledger=ledger,
        bars_by_symbol=priced({"A": 60.0, "B": 50.0, "C": 40.0, "D": 30.0, "E": 20.0, "F": 10.0}),
        strategy=PricedConviction(1),
        strategy_name="priced",
        settings=make_settings(max_positions=5, hysteresis_rank=10),
    )

    assert report.selected == 5
    # Already at its target size and still funded, so it needs no order at all.
    assert [sym for sym, _ in broker.submitted] == ["A", "B", "C", "D"]


def test_without_the_buffer_the_same_holding_is_sold(tmp_path):
    """The contrast that shows the buffer is doing the work."""
    held_shares = int(100_000 * 0.20 / 10.0)
    broker = FakeBroker(equity=100_000, positions={"F": held_shares})
    ledger = Ledger(tmp_path / "ledger.sqlite")

    run_once(
        broker=broker,
        ledger=ledger,
        bars_by_symbol=priced({"A": 60.0, "B": 50.0, "C": 40.0, "D": 30.0, "E": 20.0, "F": 10.0}),
        strategy=PricedConviction(1),
        strategy_name="priced",
        settings=make_settings(max_positions=5, hysteresis_rank=5),
    )

    assert ("F", -held_shares) in broker.submitted


def test_a_flipped_signal_is_not_protected_by_the_buffer(tmp_path):
    """Held long, now short: that is a reversal on merit, not an incumbent to shelter."""
    broker = FakeBroker(equity=100_000, positions={"C": 400})
    ledger = Ledger(tmp_path / "ledger.sqlite")

    run_once(
        broker=broker,
        ledger=ledger,
        bars_by_symbol=priced({"A": 60.0, "B": 50.0, "C": 40.0}),
        strategy=PricedConviction(-1),
        strategy_name="priced",
        settings=make_settings(max_positions=2, hysteresis_rank=10),
    )

    submitted = dict(broker.submitted)
    assert submitted["C"] == -400


# -- stale order cancellation ---------------------------------------------


def pending(ledger, symbol="AAPL", qty=20, broker_order_id="abc"):
    """Record an order the ledger believes is still resting at the broker."""
    return ledger.record_order(
        symbol=symbol,
        side="buy",
        qty=qty,
        signal_name="constant",
        signal_value=1,
        status="submitted",
        broker_order_id=broker_order_id,
    )


def test_an_order_that_never_filled_is_cancelled(tmp_path):
    """The whole point: an order resting with a rationale this cycle recomputes."""
    broker = FakeBroker(
        equity=10_000,
        fills={"abc": FillInfo(status="accepted", filled_qty=0, avg_price=0.0)},
    )
    ledger = Ledger(tmp_path / "ledger.sqlite")
    order_id = pending(ledger)

    report = run(broker, ledger, target=1, price=100.0)

    assert broker.cancelled == ["abc"]
    assert report.orders_cancelled == 1
    status = ledger._conn.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()[
        "status"
    ]
    assert status == "canceled"
    # This cycle then submits its own order, so pending is not empty: what
    # matters is that the withdrawn one is no longer in it.
    assert order_id not in [row["id"] for row in ledger.pending_orders()]


def test_a_reconciled_fill_is_not_cancelled(tmp_path):
    """Cancelling must run after reconciliation, never instead of it.

    An order that filled at today's open is a completed trade hours older than
    this cycle. Withdrawing it here would be look-ahead, and would also lose the
    fill the ledger needs to derive the position.
    """
    broker = FakeBroker(
        equity=10_000,
        positions={"AAPL": 20},
        fills={"abc": FillInfo(status="filled", filled_qty=20, avg_price=101.0)},
    )
    ledger = Ledger(tmp_path / "ledger.sqlite")
    pending(ledger)

    report = run(broker, ledger, target=1, price=100.0)

    assert broker.cancelled == []
    assert report.orders_cancelled == 0
    assert report.fills_reconciled == 1
    assert ledger.position("AAPL") == 20


def test_a_healthy_cycle_cancels_nothing(tmp_path):
    """Guards the ordering from the other side.

    Cancelling before reconciling would withdraw every order the cycle before it
    could fill, and the pipeline would submit forever and trade never. In a
    cycle where everything filled, nothing may be cancelled.
    """
    broker = FakeBroker(
        equity=10_000,
        positions={"AAPL": 20},
        fills={
            "a1": FillInfo(status="filled", filled_qty=10, avg_price=100.0),
            "a2": FillInfo(status="filled", filled_qty=10, avg_price=100.0),
        },
    )
    ledger = Ledger(tmp_path / "ledger.sqlite")
    pending(ledger, qty=10, broker_order_id="a1")
    pending(ledger, qty=10, broker_order_id="a2")

    report = run(broker, ledger, target=1, price=100.0)

    assert report.fills_reconciled == 2
    assert report.orders_cancelled == 0
    assert broker.cancelled == []


def test_an_unfilled_order_does_not_get_a_second_one_stacked_on_it(tmp_path):
    """The concrete damage cancelling prevents.

    Sizing works off the broker's position, which does not count resting orders.
    Left alone, an unfilled buy for the full target gets an identical buy added
    this cycle and both eventually fill, doubling the position past the cap that
    was supposed to bound it.
    """
    broker = FakeBroker(
        equity=10_000,
        positions={"AAPL": 0},  # the resting buy has not filled, so still flat
        fills={"abc": FillInfo(status="accepted", filled_qty=0, avg_price=0.0)},
    )
    ledger = Ledger(tmp_path / "ledger.sqlite")
    pending(ledger, qty=20)

    run(broker, ledger, target=1, price=100.0)

    # 20% of 10,000 at 100.0 is 20 shares: this cycle's order, and only it.
    assert broker.submitted == [("AAPL", 20)]
    assert broker.cancelled == ["abc"]


def test_a_halted_cycle_still_withdraws_resting_orders(tmp_path):
    """A halt stops trading; it must not leave live orders behind to fill anyway."""
    broker = FakeBroker(
        equity=10_000,
        fills={"abc": FillInfo(status="accepted", filled_qty=0, avg_price=0.0)},
    )
    ledger = Ledger(tmp_path / "ledger.sqlite")
    pending(ledger)
    ledger.trigger_halt("manual")

    report = run(broker, ledger, target=1, price=100.0)

    assert report.halted is True
    assert report.orders_cancelled == 1
    assert broker.cancelled == ["abc"]
    assert broker.submitted == []


def test_a_blocked_order_is_never_cancelled(tmp_path):
    """Blocked orders never reached the broker, so there is nothing to withdraw.

    They carry no broker_order_id, and cancelling one would rewrite a risk
    decision the ledger keeps as a record.
    """
    broker = FakeBroker(equity=10_000)
    ledger = Ledger(tmp_path / "ledger.sqlite")
    ledger.record_order(
        symbol="AAPL",
        side="buy",
        qty=20,
        signal_name="constant",
        signal_value=1,
        status="blocked",
        risk_reason="position cap",
    )

    report = run(broker, ledger, target=1, price=100.0)

    assert report.orders_cancelled == 0
    assert broker.cancelled == []


def make_ohlc(prices: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="B")
    return pd.DataFrame({"open": prices, "close": prices}, index=idx)


def cycle(sim_path, ledger, bars, target=1):
    """One cycle against the real simulated broker, rebuilt per cycle as run_live does."""
    broker = SimulatedBroker(
        sim_path, bars, cost_bps=5, slippage_bps=2, starting_cash=10_000
    )
    report = run_once(
        broker=broker,
        ledger=ledger,
        bars_by_symbol=bars,
        strategy=ConstantSignal(target),
        strategy_name="constant",
        settings=make_settings(),
    )
    position = broker.get_position("AAPL")
    broker.close()
    return report, position


def test_an_order_still_fills_across_two_real_cycles(tmp_path):
    """Integration guard against strangling the trading loop.

    FakeBroker cannot show this: it does not model an order resting until a bar
    later than its submission appears. Cycle one submits, cycle two sees a newer
    bar and fills. Were cancelling ever to move ahead of reconciliation, cycle
    two would withdraw the order instead, and the pipeline would submit forever
    and trade never while every unit test above still passed.
    """
    sim_path = tmp_path / "sim.sqlite"
    ledger = Ledger(tmp_path / "ledger.sqlite")
    prices = [100.0] * 5

    first, position = cycle(sim_path, ledger, {"AAPL": make_ohlc(prices)})
    assert first.orders_submitted == 1
    assert first.orders_cancelled == 0
    assert position == 0  # resting, not yet filled

    # Next session: one more bar exists, so the resting order can execute.
    second, position = cycle(sim_path, ledger, {"AAPL": make_ohlc(prices + [100.0])})
    assert second.fills_reconciled == 1
    assert second.orders_cancelled == 0
    assert position == 20
    assert ledger.position("AAPL") == 20


def test_an_order_the_cycle_cannot_replace_is_left_alone(tmp_path):
    """The invariant: never withdraw an order nothing will put back.

    A ticker with no bars this cycle never reaches the sizing loop, so no
    replacement order can be issued for it. Cancelling would remove the only
    live intent for that symbol and leave any position stranded, which is why
    run_live.py deliberately leaves unpriceable orphans for a human.
    """
    ledger = Ledger(tmp_path / "ledger.sqlite")
    order_id = ledger.record_order(
        symbol="DELISTED",
        side="sell",
        qty=10,
        signal_name="constant",
        signal_value=0,
        status="submitted",
        broker_order_id="sim-1",
    )
    broker = FakeBroker(
        equity=10_000,
        fills={"sim-1": FillInfo(status="accepted", filled_qty=0, avg_price=0.0)},
    )

    report = run(broker, ledger, target=1, price=100.0)

    assert broker.cancelled == []
    assert report.orders_cancelled == 0
    assert order_id in [row["id"] for row in ledger.pending_orders()]
    assert any("left pending" in note for note in report.notes)


def test_a_demoted_tickers_exit_order_is_not_withdrawn(tmp_path):
    """The regression the invariant exists to prevent.

    A ticker that left the universe keeps its bars so its exit can fill, but
    gets no fresh signal, so it never re-enters the sizing loop. Cancelling its
    resting sell would leave the position held with no order to close it and
    nothing that would ever issue one.
    """
    ledger = Ledger(tmp_path / "ledger.sqlite")
    order_id = ledger.record_order(
        symbol="SPY",
        side="sell",
        qty=26,
        signal_name="constant",
        signal_value=0,
        status="submitted",
        broker_order_id="sim-6",
    )
    broker = FakeBroker(
        equity=10_000,
        positions={"SPY": 26},
        fills={"sim-6": FillInfo(status="accepted", filled_qty=0, avg_price=0.0)},
    )

    report = run_once(
        broker=broker,
        ledger=ledger,
        bars_by_symbol={"AAPL": make_bars(100.0), "SPY": make_bars(500.0)},
        strategy=ConstantSignal(1),
        strategy_name="constant",
        settings=make_settings(),
        tradable={"AAPL"},
    )

    assert broker.cancelled == []
    assert report.orders_cancelled == 0
    assert order_id in [row["id"] for row in ledger.pending_orders()]
