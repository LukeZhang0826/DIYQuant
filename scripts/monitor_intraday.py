"""Mark the book at current prices mid-session, record it, warn if it is ugly.

The pipeline runs once a day, after the close. Between cycles nobody, including
the system, knows what the account is worth. On 2026-08-04 it fell to -8.09%
against day-start equity at 13:48 and closed at -6.95%: the worst point of the
worst day so far left no trace anywhere, because a daily snapshot only ever sees
the close.

This fills that gap. Run it on its own cron line every 15 minutes during market
hours, alongside `check_pulse.py`.

**It does not trade, and will not until two things change.** `SimulatedBroker`
stamps each order with the last daily bar's date and fills only when a later bar
appears, so an order placed at noon executes at tomorrow's open, exactly where a
23:00 order would have executed. Triggering a stop earlier would therefore
change nothing about the price. And `run_once` returns early on an active halt
*without* flattening, so a monitor that merely set the halt flag would stop the
evening cycle from flattening at all, which is worse than the current behaviour.
Both are fixable, neither is fixed here, and the `intraday_marks` this writes
are what will show whether fixing them is worth the work.

Silent unless something is worth saying, matching check_pulse.py: a monitor that
speaks every fifteen minutes is a monitor nobody reads. It alerts on the
*crossing* of a threshold, not on every run underneath it.

Exit codes: 0 = nothing to report, 1 = alert raised, 2 = could not assess.

Usage: python scripts/monitor_intraday.py [--dry-run]
"""

import argparse
import sys
from datetime import datetime, timezone

from diyquant.alerts.discord import DiscordNotifier
from diyquant.config import PROJECT_ROOT, get_secrets, get_settings
from diyquant.data.providers.yfinance_provider import fetch_last_prices
from diyquant.execution.ledger import Ledger
from diyquant.execution.sim_broker import SimulatedBroker
from diyquant.risk.intraday import assess, format_alert, mark_to_market


def _session_start(now: datetime) -> str:
    """Midnight UTC today, as the boundary between yesterday's close and today.

    Crude on purpose. The cycle records its snapshot at 23:00 UTC and the US
    session runs 13:30-20:00 UTC (14:30-21:00 outside daylight saving), so every
    run of this script falls after midnight and before that evening's snapshot.
    A calendar-aware session open would be more precise and would not change a
    single comparison.
    """
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only, send nothing")
    args = parser.parse_args()

    settings = get_settings()
    risk = settings.risk
    ledger = Ledger(PROJECT_ROOT / settings.execution.ledger_path)
    now = datetime.now(timezone.utc)
    boundary = _session_start(now)

    halt = ledger.active_halt()
    if halt is not None:
        # A halted pipeline has already flattened and will not trade until a
        # human clears it. There is no exposure to monitor and check_pulse.py
        # already reports the halt itself.
        print(f"halted since {halt['triggered_at']}: nothing to monitor")
        return 0

    anchor_row = ledger.equity_snapshot_before(boundary)
    if anchor_row is None:
        print("no equity snapshot from before today: nothing to anchor a drawdown to")
        return 2
    anchor = float(anchor_row["equity"])
    if anchor <= 0:
        print(f"anchor equity is {anchor}, refusing to divide by it")
        return 2

    # Bars are not needed: get_account is not called and nothing is priced from
    # the daily store. starting_cash is INSERT OR IGNORE, so it cannot reset an
    # existing account.
    broker = SimulatedBroker(
        PROJECT_ROOT / settings.execution.sim_db_path,
        {},
        cost_bps=settings.backtest.cost_bps,
        slippage_bps=settings.backtest.slippage_bps,
        starting_cash=settings.execution.starting_cash,
    )
    try:
        cash = broker.get_account().cash
        held = broker.open_positions()
    finally:
        broker.close()

    if not held:
        print(f"book is flat, equity {cash:,.2f}: nothing to mark")
        return 0

    prices = fetch_last_prices(sorted(held))
    equity, unpriced = mark_to_market(cash, held, prices)
    if unpriced:
        # Never assess a partial book. A missing quote on a held name makes the
        # drawdown fiction in one direction or the other, and a false breach
        # alert is how a monitor gets muted.
        print(f"could not price {', '.join(unpriced)}: refusing to assess a partial book")
        return 2

    mark = assess(
        anchor_equity=anchor,
        equity=equity,
        max_daily_drawdown_pct=risk.max_daily_drawdown_pct,
        warn_pct=risk.intraday_warn_pct,
    )
    print(
        f"anchor {anchor:,.2f} -> now {equity:,.2f} "
        f"({mark.drawdown_pct:+.2f}% vs day start, {len(held)} positions)"
    )

    # Read before writing, or this run's own mark becomes the evidence that this
    # run already alerted, and the alert never goes out.
    previous = ledger.last_intraday_mark_since(boundary)
    already_under = (
        previous is not None and float(previous["drawdown_pct"]) >= risk.intraday_warn_pct
    )

    if not args.dry_run:
        ledger.record_intraday_mark(
            equity=mark.equity,
            anchor_equity=anchor,
            drawdown_pct=mark.drawdown_pct,
            breached=mark.breached,
            ts=now.isoformat(timespec="seconds"),
        )

    if not mark.warned:
        return 0

    message = format_alert(mark, anchor, risk.max_daily_drawdown_pct)
    print(message)
    if already_under and not args.dry_run:
        print("(already alerted today, not re-sending)")
        return 1
    if args.dry_run:
        print("(dry run, nothing sent)")
        return 1
    if not settings.alerts.enabled:
        print("alerts disabled in config/settings.yaml, nothing delivered")
        return 1

    secrets = get_secrets()
    notifier = DiscordNotifier(
        secrets.discord_webhook_url,
        timeout_seconds=settings.alerts.timeout_seconds,
    )
    lines = [message]
    if secrets.dashboard_url:
        lines.append(f"dashboard: {secrets.dashboard_url}")
    print("alert delivered" if notifier.send("\n".join(lines)) else "alert NOT delivered")
    return 1


if __name__ == "__main__":
    sys.exit(main())
