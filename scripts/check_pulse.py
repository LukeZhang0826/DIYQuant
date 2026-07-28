"""Alert to Discord when the pipeline is not trading. Run on its own cron line.

Deliberately independent of the trading cycle: it reads the ledger, so it
reports correctly even when run_live.py is off cron entirely. That is the whole
point, see diyquant/alerts/pulse.py for the incident that motivated it.

Silent on a healthy day. The daily cycle already announces those, and a monitor
that speaks only when something is wrong is one whose messages get read.

Schedule it Tue-Sat so it never fires on the weekend gap: the Monday and Sunday
02:00 UTC slots would look back past Friday's cycle and cry stale every week.

Exit codes: 0 = trading normally, 1 = an alert was raised. Cron ignores these
(MAILTO is empty), but they make a manual run usable in a shell.

Usage: python scripts/check_pulse.py
"""

import sys
from datetime import datetime, timezone

from diyquant.alerts.discord import DiscordNotifier
from diyquant.alerts.pulse import pulse_alert
from diyquant.config import PROJECT_ROOT, get_secrets, get_settings
from diyquant.execution.ledger import Ledger


def main() -> int:
    settings = get_settings()
    ledger = Ledger(PROJECT_ROOT / settings.execution.ledger_path)
    snapshot = ledger.last_equity_snapshot()

    message = pulse_alert(
        halt=ledger.active_halt(),
        last_snapshot_ts=snapshot["ts"] if snapshot is not None else None,
        now=datetime.now(timezone.utc),
        stale_after_hours=settings.alerts.stale_after_hours,
    )

    if message is None:
        print("pulse ok: the pipeline traded inside the window")
        return 0

    print(message)

    # Still exit 1 when alerts are off: the condition is real whether or not
    # anyone is listening, and a manual run should say so.
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
    delivered = notifier.send("\n".join(lines))
    print("pulse alert delivered" if delivered else "pulse alert NOT delivered")
    return 1


if __name__ == "__main__":
    sys.exit(main())
