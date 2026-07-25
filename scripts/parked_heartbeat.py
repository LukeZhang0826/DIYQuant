"""Parked-mode heartbeat: a daily 'alive, not trading' ping to Discord.

While live trading is parked, run_live.py is off cron, so its per-cycle Discord
heartbeat never fires and a normal parked day is completely silent. The
healthchecks.io dead-man's switch still proves the box is alive, but only to
its own email/Discord channel and only on a state change, so a healthy parked
day produces no positive signal at all.

This sends one 'still parked, box alive' line to Discord (with the dashboard
link) so a normal parked day is visibly OK rather than silent. It is not a
trading cycle: it reads no market data and writes no ledger state.

Best-effort and never fatal: it exits 0 no matter what, so the cron line's
healthcheck ping always runs after it. Delivery itself is handled by
DiscordNotifier, which swallows every exception and sets the correct User-Agent.

Usage: python scripts/parked_heartbeat.py
"""

import sys
from datetime import date

from diyquant.alerts.discord import DiscordNotifier
from diyquant.config import get_secrets, get_settings


def main() -> int:
    settings = get_settings()
    if not settings.alerts.enabled:
        print("parked heartbeat skipped: alerts disabled in config")
        return 0

    secrets = get_secrets()
    notifier = DiscordNotifier(
        secrets.discord_webhook_url,
        timeout_seconds=settings.alerts.timeout_seconds,
    )
    lines = [f"Parked - `diyquant` alive, not trading ({date.today().isoformat()})"]
    if secrets.dashboard_url:
        lines.append(f"dashboard: {secrets.dashboard_url}")
    delivered = notifier.send("\n".join(lines))
    print("parked heartbeat delivered" if delivered else "parked heartbeat not delivered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
