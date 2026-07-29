"""Withdraw every unfilled order. Use after a cycle that submitted orders you do not want.

Why this is needed: the simulated broker's market-on-open orders rest until the
next session, and `get_order_fill` fills them unconditionally when a later bar
appears. It applies no cash check, so a cycle that submitted far more orders
than the account can fund does not simply fund the first few and stop: on the
next open every one of them executes and cash goes deeply negative.

That is exactly what the 2026-07-28 cycle queued, 466 orders against funding for
five, before the selection layer existed. Adding selection does not retract
orders already sitting at the broker, so they have to be cancelled explicitly.

Cancels at the broker first and only then marks the ledger, so an interruption
leaves orders the ledger still calls pending rather than fills the ledger has
lost sight of. Re-running is safe: an already-cancelled order cancels again to
no effect, and a filled one is left alone.

Usage: python scripts/cancel_pending_orders.py [--dry-run]
"""

import argparse
import sys

from diyquant.config import PROJECT_ROOT, get_settings
from diyquant.execution.ledger import Ledger
from diyquant.execution.sim_broker import SimulatedBroker


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only, change nothing")
    args = parser.parse_args()

    settings = get_settings()
    if settings.execution.broker != "simulated":
        print(f"refusing to run against broker '{settings.execution.broker}'")
        return 1

    ledger = Ledger(PROJECT_ROOT / settings.execution.ledger_path)
    pending = ledger.pending_orders()
    print(f"pending orders: {len(pending)}")
    if not pending or args.dry_run:
        return 0

    # No bars needed: cancelling never prices anything. starting_cash is an
    # INSERT OR IGNORE, so passing it cannot reset an existing account.
    broker = SimulatedBroker(
        PROJECT_ROOT / settings.execution.sim_db_path,
        {},
        cost_bps=settings.backtest.cost_bps,
        slippage_bps=settings.backtest.slippage_bps,
        starting_cash=settings.execution.starting_cash,
    )

    cancelled = 0
    for order in pending:
        broker_order_id = order["broker_order_id"]
        if broker_order_id:
            broker.cancel_order(broker_order_id)
        ledger.update_order_status(order["id"], "canceled")
        cancelled += 1

    broker.close()
    print(f"cancelled {cancelled} orders")
    return 0


if __name__ == "__main__":
    sys.exit(main())
