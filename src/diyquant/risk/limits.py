"""Kill-switch limits: properties of the pipeline, not features of a strategy.

Pure decision functions: account state in, allow/block decision out. No API
calls, no persistence. The live runner (Phase 2b) is responsible for storing
a triggered halt in the trade ledger and requiring a manual reset before
trading resumes.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str = ""


def check_daily_drawdown(
    day_start_equity: float,
    current_equity: float,
    max_daily_drawdown_pct: float,
) -> RiskDecision:
    """Block all trading once today's loss exceeds the configured limit.

    Drawdown is measured from the account equity at the start of the trading
    day, not from an all-time high: this is a circuit breaker for "something
    is going wrong right now", not a long-horizon performance judgment.

    The caller owns baseline freshness. Passing an equity figure from several
    days ago silently widens this into a multi-day check, so the live pipeline
    skips the call entirely once its snapshot is older than risk.max_baseline_age_hours.
    """
    if day_start_equity <= 0:
        raise ValueError(f"day_start_equity must be positive, got {day_start_equity}")

    loss_pct = (day_start_equity - current_equity) / day_start_equity * 100
    if loss_pct >= max_daily_drawdown_pct:
        return RiskDecision(
            allowed=False,
            reason=(f"daily drawdown {loss_pct:.2f}% breaches limit {max_daily_drawdown_pct:.2f}%"),
        )
    return RiskDecision(allowed=True)


def check_position_cap(
    position_value: float,
    equity: float,
    max_position_pct: float,
) -> RiskDecision:
    """Block any order that would make one symbol too large a share of equity.

    position_value is the absolute notional the symbol would have AFTER the
    order fills; sizing should already respect the cap, so a block here means
    a bug or price gap, and the order must not go out.
    """
    if equity <= 0:
        raise ValueError(f"equity must be positive, got {equity}")

    pct = abs(position_value) / equity * 100
    if pct > max_position_pct:
        return RiskDecision(
            allowed=False,
            reason=f"position {pct:.2f}% of equity breaches cap {max_position_pct:.2f}%",
        )
    return RiskDecision(allowed=True)
