"""Discord webhook alerts: a heartbeat after every cycle, loud on a halt.

Phase 3 runs the pipeline unattended under cron, so what it pushes out is the
only evidence it is alive. Delivery is best-effort by design: an alert that
fails must never take the trading cycle down with it, so send() swallows every
exception and reports success as a bool.

Uses stdlib urllib rather than requests: this is a single JSON POST and the
project has no HTTP dependency of its own.
"""

import json
import urllib.error
import urllib.request

from diyquant.execution.pipeline import CycleReport

# Discord rejects any webhook message whose content exceeds this.
MAX_CONTENT_CHARS = 2000
_TRUNCATION_MARKER = "\n... (truncated)"

# Discord requires a valid User-Agent and its Cloudflare front rejects urllib's
# default ("Python-urllib/x.y") with a 403 before the request reaches the
# webhook. The DiscordBot (url, version) form is what the API docs ask for.
USER_AGENT = "DiscordBot (https://github.com/LukeZhang0826/DIYQuant, 0.1.0)"

# Enough of an error body to identify the cause, not enough to flood cron logs.
_MAX_ERROR_BODY_CHARS = 200


def _truncate(content: str) -> str:
    """Trim to Discord's limit, keeping the head: halt status leads the message."""
    if len(content) <= MAX_CONTENT_CHARS:
        return content
    return content[: MAX_CONTENT_CHARS - len(_TRUNCATION_MARKER)] + _TRUNCATION_MARKER


def format_cycle_alert(report: CycleReport, strategy_name: str, dashboard_url: str = "") -> str:
    """Render a finished cycle as the message body.

    A halt leads with a siren because it is the one outcome demanding a human:
    the pipeline has flattened the book and will not trade again until the halt
    is cleared by hand.

    The dashboard link, when given, sits right under the header: a large-universe
    cycle can emit enough notes to overflow Discord's limit, and truncation keeps
    the head, so a link at the foot would be the first thing cut.
    """
    header = "**HALTED**" if report.halted else "Cycle OK"
    lines = [f"{header} - `{strategy_name}`"]
    if dashboard_url:
        lines.append(f"dashboard: {dashboard_url}")
    lines += [
        f"fills reconciled : {report.fills_reconciled}",
        f"orders submitted : {report.orders_submitted}",
        f"orders blocked   : {report.orders_blocked}",
        *report.notes,
    ]
    return "\n".join(lines)


class DiscordNotifier:
    """Posts messages to a Discord webhook. Never raises."""

    def __init__(self, webhook_url: str, timeout_seconds: float = 10.0, opener=None):
        # opener is injectable so tests never touch the network.
        self._webhook_url = webhook_url
        self._timeout = timeout_seconds
        self._opener = opener or urllib.request.urlopen

    @property
    def enabled(self) -> bool:
        return bool(self._webhook_url)

    def send(self, content: str) -> bool:
        """POST content to the webhook. True only when Discord accepted it."""
        if not self.enabled:
            print("discord alert skipped: no webhook URL configured")
            return False

        request = urllib.request.Request(
            self._webhook_url,
            data=json.dumps({"content": _truncate(content)}).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
            method="POST",
        )
        try:
            # A timeout is mandatory here: under cron a hung request would
            # otherwise wedge the daily job indefinitely.
            with self._opener(request, timeout=self._timeout) as response:
                return 200 <= response.status < 300
        except Exception as exc:  # noqa: BLE001 - alerting must not abort the cycle
            print(f"discord alert failed: {self._describe_failure(exc)}")
            return False

    def _describe_failure(self, exc: BaseException) -> str:
        """Describe a failure without leaking the webhook URL, which is a credential.

        Anyone holding that URL can post to the channel, and this text goes to
        cron logs, so the URL is scrubbed even from messages unlikely to carry it.
        """
        if isinstance(exc, urllib.error.HTTPError):
            # Discord explains rejections in the body; a bare status code sent us
            # guessing once already. The body never carries the webhook token.
            detail = f"HTTP {exc.code}"
            body = self._read_error_body(exc)
            if body:
                detail = f"{detail}: {body}"
        elif isinstance(exc, urllib.error.URLError):
            detail = f"{type(exc).__name__}: {exc.reason}"
        else:
            detail = type(exc).__name__
        return detail.replace(self._webhook_url, "<webhook>")

    @staticmethod
    def _read_error_body(exc: urllib.error.HTTPError) -> str:
        """Best-effort body text. Reading it must not itself raise."""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - diagnostics are never worth an exception
            return ""
        return " ".join(body.split())[:_MAX_ERROR_BODY_CHARS]
