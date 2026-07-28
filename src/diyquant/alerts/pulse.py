"""Is the pipeline actually trading? A liveness check that survives the trading job.

The failure this exists for: on 2026-07-25 the trading cycle was swapped out of
cron for a parked-mode heartbeat that always exits 0. The healthchecks.io
dead-man's switch kept going green, Discord kept reporting "alive", and the
pipeline did not trade for four days without one alert. Every liveness signal
was attached to whatever ran at 23:00, so replacing that job quietly turned the
monitoring into a report on itself.

The fix is to check a fact that only real trading can produce. A cycle writes an
equity snapshot to the ledger; nothing that merely exits 0 can. So this reads
the ledger rather than watching a process, and stays honest no matter what cron
is currently pointed at.

Pure functions, no I/O: the wiring lives in scripts/check_pulse.py. Alert-only
by design. A healthy day is silent here because the cycle's own heartbeat
already reports it, so anything this says means the pipeline is not trading.
"""

from collections.abc import Mapping
from datetime import datetime, timezone


def hours_since(ts: str, now: datetime) -> float:
    """Hours between an ISO-8601 ledger timestamp and now.

    Ledger timestamps carry an offset (`+00:00`), but a naive one is treated as
    UTC rather than raising: a monitor that crashes on an odd row is worse than
    one that reports a slightly wrong age.
    """
    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (now - parsed).total_seconds() / 3600.0


def pulse_alert(
    halt: Mapping | None,
    last_snapshot_ts: str | None,
    now: datetime,
    stale_after_hours: float,
) -> str | None:
    """The message to send, or None when the pipeline is trading normally.

    Ordered by what a reader needs first. A halt is deliberate and explains
    itself, so it outranks staleness: a halted pipeline is also stale, and
    reporting the staleness would bury the reason.
    """
    if halt is not None:
        return (
            f"NOT TRADING: halt active since {halt['triggered_at']}. "
            f"Reason: {halt['reason']}. "
            "A halt stops trading until a human clears it, by design."
        )

    if last_snapshot_ts is None:
        return (
            "NOT TRADING: no cycle has ever completed. "
            "The ledger holds no equity snapshot, so the pipeline has not run once."
        )

    age = hours_since(last_snapshot_ts, now)
    if age > stale_after_hours:
        return (
            f"NOT TRADING: last cycle {age:.0f}h ago, past the {stale_after_hours:.0f}h limit. "
            "Check `crontab -l` still runs scripts/run_live.py, "
            "then `tail -80 ~/diyquant-cron.log`."
        )

    return None
