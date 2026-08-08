"""Clear an active kill-switch halt so the next cycle trades again.

The halt is the one piece of state the pipeline will never undo by itself, on
purpose: `run_once` sees an uncleared halt and returns immediately, every cycle,
forever, until a human decides the reason for it has been dealt with. That is
the whole value of a kill-switch. Automating the reset would make it a speed
bump instead of a stop.

Until 2026-08-08 there was no procedure for the reset at all, only a
`Ledger.clear_halt` method and no way to reach it on the box. The 2026-08-04
halt sat uncleared for four sessions partly for that reason. A stop with no
documented way to resume is a stop that gets cleared by hand with a raw UPDATE
at the worst possible moment, so it lives here instead.

What this deliberately does NOT do is flatten, re-enter, or place any order. The
kill-switch already flattened the book on the way in. This only removes the
block, and the next scheduled cycle rebuilds a position from scratch on that
day's signals, sized by that day's rules.

Read the report before clearing. Resuming into the same conditions that caused
the halt, with the same configuration, will halt again, and the second one tells
you nothing the first did not.

Usage:
  python scripts/clear_halt.py            # show the active halt, change nothing
  python scripts/clear_halt.py --confirm  # clear it
"""

import argparse
import sys

from diyquant.config import PROJECT_ROOT, get_settings
from diyquant.execution.ledger import Ledger


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="actually clear the halt; without it this only reports",
    )
    args = parser.parse_args()

    settings = get_settings()
    ledger = Ledger(PROJECT_ROOT / settings.execution.ledger_path)

    halt = ledger.active_halt()
    if halt is None:
        print("no active halt: the pipeline is already free to trade")
        return 0

    print(f"active halt #{halt['id']}")
    print(f"  triggered : {halt['triggered_at']}")
    print(f"  reason    : {halt['reason']}")

    if not args.confirm:
        print("\nreporting only. re-run with --confirm to clear it.")
        return 0

    ledger.clear_halt(int(halt["id"]))
    print(f"\ncleared halt #{halt['id']}. the next cycle will trade.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
