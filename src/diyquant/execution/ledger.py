"""Trade ledger: SQLite record of every order, fill, equity snapshot, and halt.

Append-only by design: positions and P&L are always derived by replaying fills,
never stored and edited. The two allowed mutations are order status transitions
(submitted -> filled/canceled, recorded as the broker reports them) and clearing
a halt (a deliberate manual step). Fills and equity snapshots are never touched.

This file is also the future tax record: fills carry everything needed to
rebuild cost-basis lots (timestamp, symbol, side, qty, price, fees).
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    qty INTEGER NOT NULL CHECK (qty > 0),
    signal_name TEXT NOT NULL,
    signal_value INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('blocked', 'submitted', 'filled', 'canceled')),
    risk_reason TEXT NOT NULL DEFAULT '',
    broker_order_id TEXT
);
CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    ts TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    qty INTEGER NOT NULL CHECK (qty > 0),
    price REAL NOT NULL,
    fees REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS equity_snapshots (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    cash REAL NOT NULL,
    equity REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS halts (
    id INTEGER PRIMARY KEY,
    triggered_at TEXT NOT NULL,
    reason TEXT NOT NULL,
    cleared_at TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Ledger:
    def __init__(self, path: Path | str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # -- orders ------------------------------------------------------------

    def record_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        signal_name: str,
        signal_value: int,
        status: str,
        risk_reason: str = "",
        broker_order_id: str | None = None,
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO orders (ts, symbol, side, qty, signal_name, signal_value,"
            " status, risk_reason, broker_order_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                _now(),
                symbol,
                side,
                qty,
                signal_name,
                signal_value,
                status,
                risk_reason,
                broker_order_id,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def update_order_status(self, order_id: int, status: str) -> None:
        self._conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        self._conn.commit()

    def pending_orders(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM orders WHERE status = 'submitted' ORDER BY id"
        ).fetchall()

    # -- fills -------------------------------------------------------------

    def record_fill(
        self, order_id: int, symbol: str, side: str, qty: int, price: float, fees: float = 0.0
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO fills (order_id, ts, symbol, side, qty, price, fees)"
            " VALUES (?,?,?,?,?,?,?)",
            (order_id, _now(), symbol, side, qty, price, fees),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def position(self, symbol: str) -> int:
        """Net shares implied by recorded fills; reconciles against the broker."""
        row = self._conn.execute(
            "SELECT COALESCE(SUM(CASE side WHEN 'buy' THEN qty ELSE -qty END), 0) AS net"
            " FROM fills WHERE symbol = ?",
            (symbol,),
        ).fetchone()
        return int(row["net"])

    # -- equity ------------------------------------------------------------

    def record_equity_snapshot(self, cash: float, equity: float) -> None:
        self._conn.execute(
            "INSERT INTO equity_snapshots (ts, cash, equity) VALUES (?,?,?)",
            (_now(), cash, equity),
        )
        self._conn.commit()

    def last_equity(self) -> float | None:
        row = self._conn.execute(
            "SELECT equity FROM equity_snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return float(row["equity"]) if row else None

    # -- halts -------------------------------------------------------------

    def trigger_halt(self, reason: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO halts (triggered_at, reason) VALUES (?,?)", (_now(), reason)
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def active_halt(self) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM halts WHERE cleared_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()

    def clear_halt(self, halt_id: int) -> None:
        """Manual step: only a human decides trading may resume."""
        self._conn.execute("UPDATE halts SET cleared_at = ? WHERE id = ?", (_now(), halt_id))
        self._conn.commit()
