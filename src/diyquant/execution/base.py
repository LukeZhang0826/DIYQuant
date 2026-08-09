"""Broker interface. Swapping paper -> live is a config change, never a code change."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AccountState:
    cash: float
    equity: float


@dataclass(frozen=True)
class OrderResult:
    broker_order_id: str
    status: str


@dataclass(frozen=True)
class FillInfo:
    status: str
    filled_qty: int
    avg_price: float


class Broker(Protocol):
    def get_account(self) -> AccountState: ...

    def get_position(self, symbol: str) -> int:
        """Signed shares currently held; 0 when flat."""
        ...

    def submit_market_order(self, symbol: str, qty: int) -> OrderResult:
        """Submit a market-on-open order. qty is signed: positive buys, negative sells.

        Market-on-open is deliberate: a signal computed from bar T's close must
        execute at bar T+1's open at the earliest (no look-ahead).
        """
        ...

    def get_order_fill(self, broker_order_id: str) -> FillInfo:
        """Current status and fill details for a previously submitted order."""
        ...

    def cancel_order(self, broker_order_id: str) -> None:
        """Withdraw an order that has not filled. Filled orders are immutable.

        Part of the interface rather than one broker's extra, because the
        pipeline cancels every cycle: a broker that cannot withdraw a resting
        order cannot be swapped in without silently changing what the pipeline
        does. Must tolerate being called on an order that already filled or was
        already cancelled, since it runs on whatever the ledger still believes
        is pending.
        """
        ...

    def open_order_ids(self) -> set[str]:
        """Every order the broker still considers live, as broker order ids.

        The ledger records what we *intended*; this is what the venue will
        actually still execute. Nothing else can answer that question: fills are
        looked up one id at a time, and only from ids the ledger already knows
        about, so an order the ledger has lost sight of is invisible to every
        other call in this interface. That is not hypothetical. On 2026-08-09
        the simulated broker was found holding 472 orders it still considered
        live that the ledger had recorded as cancelled two weeks earlier, from
        before `cancel_order` existed.
        """
        ...
