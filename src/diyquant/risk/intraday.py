"""Mark the book mid-session and decide whether that is worth saying out loud.

Between the 19:00 Toronto cycles the system is blind. On 2026-08-04 the account
fell to **-8.09%** against its day-start equity at 13:48 and recovered to -6.95%
by the close, and nothing anywhere recorded that the deeper excursion had ever
happened. The daily snapshot only ever sees the close, so the worst moment of a
bad day is invisible by construction.

This module supplies the two pure pieces: value the book at current prices, and
judge the result against the same limit the daily kill-switch uses. Fetching
prices, storing the mark and sending the alert belong to
`scripts/monitor_intraday.py`, in the same split `alerts/pulse.py` uses.

**This observes, it does not act, and that is deliberate rather than
unfinished.** Two things would have to change first:

- `SimulatedBroker` fills at the *next* daily open, stamping each order with the
  last bar's date. An order placed at noon executes at tomorrow's open, the same
  price a 23:00 order gets, so triggering earlier would buy nothing.
- `run_once` returns early on an active halt *without* flattening. A monitor
  that merely set the halt flag would therefore stop the evening cycle from
  flattening the book, which is strictly worse than today.

So the value here is the record and the warning, and the record is what will
eventually say whether an intraday stop is worth the broker work: how often the
book breaches mid-session and then recovers is not currently known by anyone.
"""

from dataclasses import dataclass

from diyquant.risk.limits import check_daily_drawdown


@dataclass(frozen=True)
class IntradayMark:
    equity: float
    drawdown_pct: float  # positive is a loss against the day-start anchor
    breached: bool  # past the daily kill-switch limit
    warned: bool  # past the softer warning threshold
    reason: str = ""


def mark_to_market(
    cash: float,
    positions: dict[str, int],
    prices: dict[str, float],
) -> tuple[float, list[str]]:
    """Value the book at the given prices. Returns (equity, symbols not priced).

    A held symbol with no usable price is reported rather than skipped, and the
    caller must refuse to judge a drawdown until the list is empty. Silently
    valuing it at zero would read as a total loss on that name and could raise a
    false alarm off nothing worse than one failed quote; silently dropping it
    would understate a real loss. Neither is safe, so neither is done here.

    A non-positive or NaN price counts as not priced: yfinance returns 0.0 and
    NaN often enough on a thin symbol that treating them as real would put
    fictional numbers into an alert.
    """
    equity = cash
    unpriced: list[str] = []
    for symbol, qty in positions.items():
        if qty == 0:
            continue
        price = prices.get(symbol)
        if price is None or price != price or price <= 0:  # NaN != NaN
            unpriced.append(symbol)
            continue
        equity += qty * price
    return equity, sorted(unpriced)


def assess(
    anchor_equity: float,
    equity: float,
    max_daily_drawdown_pct: float,
    warn_pct: float,
) -> IntradayMark:
    """Judge a marked book against the day-start anchor.

    The limit test is `check_daily_drawdown`, the exact function the daily
    kill-switch calls, so the intraday view can never disagree with the evening
    one about what counts as a breach.

    `anchor_equity` must be the last snapshot from *before* today's session, not
    simply the most recent one. That distinction is the whole hazard of running
    this often: anchored to a mark from fifteen minutes ago, a 3% daily limit
    quietly becomes "3% in fifteen minutes" and a slow bleed across a session
    never trips anything. `Ledger.equity_snapshot_before` exists for this.
    """
    decision = check_daily_drawdown(anchor_equity, equity, max_daily_drawdown_pct)
    drawdown_pct = (anchor_equity - equity) / anchor_equity * 100
    return IntradayMark(
        equity=equity,
        drawdown_pct=drawdown_pct,
        breached=not decision.allowed,
        warned=drawdown_pct >= warn_pct,
        reason=decision.reason,
    )


def format_alert(mark: IntradayMark, anchor_equity: float, limit_pct: float) -> str:
    """Render a mark as the Discord message body.

    Says explicitly that nothing was traded. An alert that reads like an action
    invites the reader to assume the position is already closed, and it is not.
    """
    header = "**INTRADAY BREACH**" if mark.breached else "Intraday warning"
    return "\n".join(
        [
            f"{header} - book is {mark.drawdown_pct:.2f}% below day-start equity",
            f"day-start : {anchor_equity:,.0f}",
            f"now       : {mark.equity:,.0f}",
            f"limit     : {limit_pct:.2f}%",
            "",
            "No orders were placed. This is a monitor: the evening cycle still owns"
            " the kill-switch and the flatten.",
        ]
    )
