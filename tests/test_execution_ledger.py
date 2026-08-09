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


def test_last_equity_snapshot_carries_timestamp(tmp_path):
    ledger = make_ledger(tmp_path)
    assert ledger.last_equity_snapshot() is None
    ledger.record_equity_snapshot(cash=5_000, equity=10_000, ts="2026-07-01T00:00:00+00:00")
    row = ledger.last_equity_snapshot()
    assert row["equity"] == 10_000
    assert row["ts"] == "2026-07-01T00:00:00+00:00"


def test_halt_lifecycle(tmp_path):
    ledger = make_ledger(tmp_path)
    assert ledger.active_halt() is None
    halt_id = ledger.trigger_halt("daily drawdown 4.00% breaches limit 3.00%")
    assert ledger.active_halt()["id"] == halt_id
    ledger.clear_halt(halt_id)
    assert ledger.active_halt() is None


def test_news_scores_are_archived_raw(tmp_path):
    """Stored per headline, not as the decayed aggregate the gate consumes.

    The aggregate depends on half_life_hours and the source whitelist, and tuning
    those is the whole point of keeping the archive. Storing only the output
    would bake today's settings permanently into the record.
    """
    ledger = Ledger(tmp_path / "ledger.sqlite")
    ledger.record_news_scores(
        "AAPL",
        [
            ("2026-08-01T12:00:00+00:00", "benzinga", "Apple beats on earnings", 0.8),
            ("2026-08-01T13:00:00+00:00", "reuters", "Apple faces probe", -0.6),
        ],
    )
    rows = ledger.news_scores()
    assert [r["score"] for r in rows] == [0.8, -0.6]
    assert rows[0]["headline"] == "Apple beats on earnings"
    assert rows[1]["source"] == "reuters"


def test_the_same_headline_is_not_archived_twice(tmp_path):
    """Cycles overlap their lookback window, so headlines repeat every run.

    Without this the archive would count one story as many, which is exactly the
    distortion a future sentiment backtest cannot see and cannot correct for.
    """
    ledger = Ledger(tmp_path / "ledger.sqlite")
    item = [("2026-08-01T12:00:00+00:00", "benzinga", "Apple beats on earnings", 0.8)]

    ledger.record_news_scores("AAPL", item)
    ledger.record_news_scores("AAPL", item)

    assert len(ledger.news_scores()) == 1


def test_the_same_headline_counts_once_per_symbol(tmp_path):
    """A story naming two companies is evidence about each of them."""
    ledger = Ledger(tmp_path / "ledger.sqlite")
    item = [("2026-08-01T12:00:00+00:00", "reuters", "Chip supply deal signed", 0.4)]

    ledger.record_news_scores("NVDA", item)
    ledger.record_news_scores("AMD", item)

    assert {r["symbol"] for r in ledger.news_scores()} == {"NVDA", "AMD"}


def test_anchor_ignores_snapshots_from_today(tmp_path):
    """The property that keeps a frequent monitor from breaking the daily limit.

    Anchored to the most recent snapshot, a check at 15:00 would measure the loss
    since 14:45 and call it a daily drawdown. equity_snapshot_before pins it to
    the last one from before today instead.
    """
    ledger = make_ledger(tmp_path)
    ledger.record_equity_snapshot(cash=0, equity=100_000, ts="2026-08-03T23:00:00+00:00")
    ledger.record_equity_snapshot(cash=0, equity=95_000, ts="2026-08-04T14:45:00+00:00")

    anchor = ledger.equity_snapshot_before("2026-08-04T00:00:00+00:00")
    assert float(anchor["equity"]) == 100_000

    # last_equity_snapshot is the trap this exists to avoid.
    assert float(ledger.last_equity_snapshot()["equity"]) == 95_000


def test_anchor_is_none_before_any_history(tmp_path):
    ledger = make_ledger(tmp_path)
    ledger.record_equity_snapshot(cash=0, equity=100_000, ts="2026-08-04T14:45:00+00:00")
    assert ledger.equity_snapshot_before("2026-08-04T00:00:00+00:00") is None


def test_intraday_marks_do_not_become_the_daily_baseline(tmp_path):
    """Marks live in their own table, so the kill-switch never sees them."""
    ledger = make_ledger(tmp_path)
    ledger.record_equity_snapshot(cash=0, equity=100_000, ts="2026-08-03T23:00:00+00:00")
    ledger.record_intraday_mark(
        equity=94_000,
        anchor_equity=100_000,
        drawdown_pct=6.0,
        breached=True,
        ts="2026-08-04T17:00:00+00:00",
    )
    assert float(ledger.last_equity_snapshot()["equity"]) == 100_000


def test_last_mark_since_finds_todays_worst_reported(tmp_path):
    ledger = make_ledger(tmp_path)
    ledger.record_intraday_mark(
        equity=99_000,
        anchor_equity=100_000,
        drawdown_pct=1.0,
        breached=False,
        ts="2026-08-03T17:00:00+00:00",
    )
    ledger.record_intraday_mark(
        equity=97_500,
        anchor_equity=100_000,
        drawdown_pct=2.5,
        breached=False,
        ts="2026-08-04T15:00:00+00:00",
    )
    since = ledger.last_intraday_mark_since("2026-08-04T00:00:00+00:00")
    assert float(since["drawdown_pct"]) == 2.5
    assert ledger.last_intraday_mark_since("2026-08-05T00:00:00+00:00") is None
