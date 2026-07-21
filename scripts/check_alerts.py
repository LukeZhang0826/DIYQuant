"""Smoke-check the Discord alerting path. Run after any deploy or config change.

Sends a real message, so the channel itself is the proof. Unit tests inject a
fake HTTP opener and so cannot verify that Discord accepts what we send: that
gap is exactly how the missing User-Agent reached a working tree. This script
closes it.

Exits 0 only when Discord accepted the message, so it can gate a deploy script.

Usage: python scripts/check_alerts.py
"""

import socket
import sys
from datetime import datetime, timezone

from diyquant.alerts.discord import DiscordNotifier
from diyquant.config import get_secrets, get_settings


def main() -> int:
    settings = get_settings()
    webhook_url = get_secrets().discord_webhook_url

    # Never print the URL itself: it is a credential, and this output is meant
    # to be pasted into issues and read off cron logs.
    print(f"alerts enabled    : {settings.alerts.enabled}")
    print(f"webhook configured: {bool(webhook_url)}")
    print(f"timeout           : {settings.alerts.timeout_seconds}s")

    if not settings.alerts.enabled:
        print("\nFAIL: alerts are disabled in config/settings.yaml, so no cycle will report.")
        return 1
    if not webhook_url:
        print("\nFAIL: DISCORD_WEBHOOK_URL is unset in .env, so alerting is a silent no-op.")
        return 1

    # The hostname is the point on a remote box: it proves the message came from
    # the instance under test and not from a laptop that happens to share a .env.
    host = socket.gethostname()
    sent_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    notifier = DiscordNotifier(webhook_url, timeout_seconds=settings.alerts.timeout_seconds)

    print(f"\nsending test alert as `{host}` ...")
    delivered = notifier.send(f"DIYQuant alert check from `{host}` at {sent_at}")

    if not delivered:
        print("FAIL: Discord did not accept the message (reason above).")
        return 1
    print(f"OK: delivered. Confirm a message from `{host}` appears in the channel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
