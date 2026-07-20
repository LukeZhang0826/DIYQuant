"""Simulated paper broker: real market prices, simulated account.

Alpaca's paper engine is unavailable to Canadian residents, and is itself a
simulation; this adapter provides the same thing locally. Orders fill at the
next trading day's real open plus slippage, commission mirrors the backtest's
cost_bps, and account state (cash, positions, orders) persists in its own
SQLite file, separate from the ledger: the ledger is our diary, this file
plays the exchange's books.

An order submitted after bar T fills when a bar dated later than T appears in
the data (normally the next run), preserving the no-look-ahead rule exactly
as the backtester does with shift(1).
"""

import sqlite3
from pathlib import Path

import pandas as pd

from diyquant.execution.base import AccountState, FillInfo, OrderResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY CHECK (id = 1), cash REAL NOT NULL);
CREATE TABLE IF NOT EXISTS positions (symbol TEXT PRIMARY KEY, qty INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    symbol TEXT NOT NULL,
    qty INTEGER NOT NULL,
    submitted_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('accepted', 'filled')),
    fill_price REAL,
    fees REAL
);
"""


class SimulatedBroker:
    def __init__(
        self,
        path: Path | str,
        bars_by_symbol: dict[str, pd.DataFrame],
        cost_bps: float,
        slippage_bps: float,
        starting_cash: float,
    ):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.execute(
            "INSERT OR IGNORE INTO account (id, cash) VALUES (1, ?)", (starting_cash,)
        )
        self._conn.commit()
        self._bars = bars_by_symbol
        self._cost = cost_bps / 10_000
        self._slip = slippage_bps / 10_000

    def get_account(self) -> AccountState:
        cash = float(self._conn.execute("SELECT cash FROM account").fetchone()["cash"])
        positions_value = 0.0
        for row in self._conn.execute("SELECT symbol, qty FROM positions"):
            bars = self._bars.get(row["symbol"])
            if bars is not None and row["qty"] != 0:
                positions_value += row["qty"] * float(bars["close"].iloc[-1])
        return AccountState(cash=cash, equity=cash + positions_value)

    def get_position(self, symbol: str) -> int:
        row = self._conn.execute("SELECT qty FROM positions WHERE symbol = ?", (symbol,)).fetchone()
        return int(row["qty"]) if row else 0

    def submit_market_order(self, symbol: str, qty: int) -> OrderResult:
        if qty == 0:
            raise ValueError("qty must be non-zero")
        submitted_date = self._bars[symbol].index[-1].date().isoformat()
        cur = self._conn.execute(
            "INSERT INTO orders (symbol, qty, submitted_date, status) VALUES (?,?,?,'accepted')",
            (symbol, qty, submitted_date),
        )
        self._conn.commit()
        return OrderResult(broker_order_id=f"sim-{cur.lastrowid}", status="accepted")

    def get_order_fill(self, broker_order_id: str) -> FillInfo:
        order_id = int(broker_order_id.removeprefix("sim-"))
        order = self._conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if order is None:
            raise ValueError(f"unknown order {broker_order_id}")
        if order["status"] == "filled":
            return FillInfo(
                status="filled",
                filled_qty=abs(order["qty"]),
                avg_price=float(order["fill_price"]),
            )

        bars = self._bars[order["symbol"]]
        later = bars[bars.index.date.astype(str) > order["submitted_date"]]
        if later.empty:
            return FillInfo(status="accepted", filled_qty=0, avg_price=0.0)

        qty = int(order["qty"])
        open_price = float(later["open"].iloc[0])
        price = open_price * (1 + self._slip) if qty > 0 else open_price * (1 - self._slip)
        fees = abs(qty) * price * self._cost

        self._conn.execute("UPDATE account SET cash = cash - ? WHERE id = 1", (qty * price + fees,))
        self._conn.execute(
            "INSERT INTO positions (symbol, qty) VALUES (?, ?)"
            " ON CONFLICT(symbol) DO UPDATE SET qty = qty + excluded.qty",
            (order["symbol"], qty),
        )
        self._conn.execute(
            "UPDATE orders SET status = 'filled', fill_price = ?, fees = ? WHERE id = ?",
            (price, fees, order_id),
        )
        self._conn.commit()
        return FillInfo(status="filled", filled_qty=abs(qty), avg_price=price)

    def close(self) -> None:
        self._conn.close()
