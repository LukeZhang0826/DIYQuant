from datetime import datetime, timedelta, timezone

from diyquant.alerts.pulse import hours_since, pulse_alert

NOW = datetime(2026, 7, 28, 23, 0, tzinfo=timezone.utc)


def ts(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).isoformat()


def test_recent_cycle_is_silent():
    assert pulse_alert(None, ts(3), NOW, 30.0) is None


def test_cycle_just_inside_the_window_is_silent():
    assert pulse_alert(None, ts(29.9), NOW, 30.0) is None


def test_stale_cycle_alerts_with_its_age():
    message = pulse_alert(None, ts(117), NOW, 30.0)
    assert message is not None
    assert "NOT TRADING" in message
    assert "117h ago" in message
    # The alert has to say what to look at; a bare "stale" reads as noise.
    assert "run_live.py" in message


def test_halt_outranks_staleness():
    """A halted pipeline is also stale. Reporting the staleness buries the reason."""
    halt = {"reason": "daily drawdown 4.00% breaches limit 3.00%", "triggered_at": ts(200)}
    message = pulse_alert(halt, ts(200), NOW, 30.0)
    assert message is not None
    assert "halt active" in message
    assert "daily drawdown 4.00%" in message
    assert "h ago" not in message


def test_never_run_is_distinct_from_stale():
    message = pulse_alert(None, None, NOW, 30.0)
    assert message is not None
    assert "no cycle has ever completed" in message


def test_the_parked_incident_would_have_alerted():
    """The regression this module exists for: 2026-07-24 cycle, still parked on 07-28."""
    last_cycle = datetime(2026, 7, 24, 1, 45, tzinfo=timezone.utc)
    message = pulse_alert(None, last_cycle.isoformat(), NOW, 30.0)
    assert message is not None and "NOT TRADING" in message


def test_hours_since_treats_a_naive_timestamp_as_utc():
    assert hours_since("2026-07-28T20:00:00", NOW) == 3.0
    assert hours_since("2026-07-28T20:00:00+00:00", NOW) == 3.0
    assert hours_since("2026-07-28T20:00:00Z", NOW) == 3.0
