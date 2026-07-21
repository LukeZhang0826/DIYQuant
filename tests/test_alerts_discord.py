import json
import urllib.error

import io

from diyquant.alerts.discord import (
    MAX_CONTENT_CHARS,
    USER_AGENT,
    DiscordNotifier,
    format_cycle_alert,
)
from diyquant.execution.pipeline import CycleReport

WEBHOOK = "https://discord.com/api/webhooks/123/secret-token"


class FakeResponse:
    def __init__(self, status=204):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class FakeOpener:
    """Stands in for urllib.request.urlopen so tests never touch the network."""

    def __init__(self, status=204, raises=None):
        self.status = status
        self.raises = raises
        self.calls: list[tuple] = []

    def __call__(self, request, timeout=None):
        self.calls.append((request, timeout))
        if self.raises is not None:
            raise self.raises
        return FakeResponse(self.status)


def payload_of(request) -> dict:
    return json.loads(request.data.decode("utf-8"))


# -- formatting ------------------------------------------------------------


def test_format_reports_counts_for_a_clean_cycle():
    report = CycleReport(fills_reconciled=2, orders_submitted=3, orders_blocked=1)
    text = format_cycle_alert(report, "sma_crossover")
    assert "Cycle OK" in text
    assert "sma_crossover" in text
    assert "fills reconciled : 2" in text
    assert "orders submitted : 3" in text


def test_format_leads_with_halt_and_keeps_notes():
    """A halt is the one outcome needing a human, so it must lead the message."""
    report = CycleReport(halted=True, notes=["KILL SWITCH: daily drawdown 4.10% breaches limit"])
    text = format_cycle_alert(report, "sma_crossover")
    assert text.startswith("**HALTED**")
    assert "KILL SWITCH" in text


def test_long_content_is_truncated_to_discord_limit():
    """Discord 400s on an over-long message, which would lose the alert entirely."""
    notifier = DiscordNotifier(WEBHOOK, opener=(opener := FakeOpener()))
    notifier.send("x" * 5000)
    content = payload_of(opener.calls[0][0])["content"]
    assert len(content) == MAX_CONTENT_CHARS
    assert content.endswith("(truncated)")


# -- delivery --------------------------------------------------------------


def test_send_posts_json_to_the_webhook_with_a_timeout():
    notifier = DiscordNotifier(WEBHOOK, timeout_seconds=7, opener=(opener := FakeOpener()))
    assert notifier.send("hello") is True

    request, timeout = opener.calls[0]
    assert request.full_url == WEBHOOK
    assert request.get_method() == "POST"
    assert request.headers["Content-type"] == "application/json"
    assert payload_of(request) == {"content": "hello"}
    # Without a timeout a hung webhook would wedge the cron job indefinitely.
    assert timeout == 7


def test_send_is_a_noop_without_a_webhook_url():
    notifier = DiscordNotifier("", opener=(opener := FakeOpener()))
    assert notifier.enabled is False
    assert notifier.send("hello") is False
    assert opener.calls == []


def test_send_identifies_itself_with_a_user_agent():
    """urllib's default UA is 403'd by Discord's Cloudflare front before it
    ever reaches the webhook. Observed live on 2026-07-21."""
    notifier = DiscordNotifier(WEBHOOK, opener=(opener := FakeOpener()))
    notifier.send("hello")

    request = opener.calls[0][0]
    assert request.headers["User-agent"] == USER_AGENT
    assert "urllib" not in request.headers["User-agent"]


def test_http_error_is_swallowed_so_the_cycle_survives():
    error = urllib.error.HTTPError(WEBHOOK, 429, "Too Many Requests", {}, None)
    notifier = DiscordNotifier(WEBHOOK, opener=FakeOpener(raises=error))
    assert notifier.send("hello") is False


def test_http_error_output_includes_the_response_body(capsys):
    """A bare status code is not diagnosable: Discord explains itself in the body."""
    body = io.BytesIO(b'{"message": "You are being rate limited.", "code": 0}')
    error = urllib.error.HTTPError(WEBHOOK, 429, "Too Many Requests", {}, body)
    notifier = DiscordNotifier(WEBHOOK, opener=FakeOpener(raises=error))

    assert notifier.send("hello") is False

    out = capsys.readouterr().out
    assert "HTTP 429" in out
    assert "rate limited" in out


def test_unreadable_error_body_still_reports_the_status(capsys):
    """Reading diagnostics must never raise on top of the original failure."""
    error = urllib.error.HTTPError(WEBHOOK, 500, "Server Error", {}, None)
    notifier = DiscordNotifier(WEBHOOK, opener=FakeOpener(raises=error))

    assert notifier.send("hello") is False
    assert "HTTP 500" in capsys.readouterr().out


def test_network_failure_is_swallowed_so_the_cycle_survives():
    notifier = DiscordNotifier(WEBHOOK, opener=FakeOpener(raises=urllib.error.URLError("no route")))
    assert notifier.send("hello") is False


def test_unexpected_exception_is_swallowed_so_the_cycle_survives():
    """Alerting is best-effort: nothing it raises may abort a trading cycle."""
    notifier = DiscordNotifier(WEBHOOK, opener=FakeOpener(raises=RuntimeError("boom")))
    assert notifier.send("hello") is False


def test_non_2xx_status_is_not_reported_as_delivered():
    notifier = DiscordNotifier(WEBHOOK, opener=FakeOpener(status=302))
    assert notifier.send("hello") is False


def test_failure_output_never_leaks_the_webhook_url(capsys):
    """The webhook URL is a credential and this text goes to cron logs."""
    leaky = urllib.error.URLError(f"cannot connect to {WEBHOOK}")
    notifier = DiscordNotifier(WEBHOOK, opener=FakeOpener(raises=leaky))

    assert notifier.send("hello") is False

    out = capsys.readouterr().out
    assert "secret-token" not in out
    assert "<webhook>" in out
