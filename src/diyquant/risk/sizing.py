"""Position sizing: turn a signal's target {-1, 0, +1} into a whole-share count.

Pure functions. The cap comes from config (risk.max_position_pct); sizing to
the cap rather than full equity is what keeps any single symbol from sinking
the account.

A flat cap is not enough on its own, and 2026-08-04 is the proof. Five slots at
20% of equity each, held against a 3% daily kill-switch, means one name moving
15% trips the switch by itself. COHR gapped 13.1% overnight while the book was
short 22% of equity in it, and the halt fired before the market had traded a
single share. The cap was sized in dollars while the limit it has to respect is
denominated in risk, and those are only the same number for a name of average
volatility.

`volatility_budget_pct` reconciles the two. Each position gets the notional that
makes its expected daily move worth `target_risk_pct` of equity, so a sleepy
name gets the full cap and a name swinging 6% a day gets a fraction of it. The
flat cap stays on top as a hard backstop: volatility scaling can only ever ask
for less.
"""

import math

import pandas as pd

DEFAULT_VOL_LOOKBACK = 20


def realized_vol_pct(close: pd.Series, lookback: int = DEFAULT_VOL_LOOKBACK) -> pd.Series:
    """Rolling standard deviation of daily simple returns, in percent.

    Simple returns, not log, to match how the portfolio backtester compounds a
    book. The first `lookback` entries are NaN, which callers must treat as
    "unknown", never as "calm": see `volatility_budget_pct`.
    """
    if lookback < 2:
        raise ValueError(f"lookback must be at least 2, got {lookback}")
    return close.pct_change().rolling(lookback).std() * 100


def volatility_budget_pct(
    daily_vol_pct: float,
    target_risk_pct: float,
    max_position_pct: float,
) -> float:
    """Return the share of equity this symbol may occupy, in percent.

    The position is sized so that a one-standard-deviation day in the symbol
    moves the account by about `target_risk_pct`. At target 0.4% and a name with
    2% daily volatility that is 20% of equity; the same target on a 6% name is
    6.7%. Never more than `max_position_pct`, so this only ever de-risks.

    `target_risk_pct` of 0 disables scaling and returns the flat cap, which is
    what the pre-2026-08-08 pipeline did and what the ablation baseline needs.

    An unknown volatility (NaN, meaning fewer bars than the lookback) returns 0:
    a name we cannot size is a name we do not hold. Defaulting the other way
    would hand the maximum position to precisely the symbols we know least
    about. A genuinely zero volatility is different and does get the full cap,
    since a price that does not move cannot breach a risk budget.
    """
    if max_position_pct <= 0:
        raise ValueError(f"max_position_pct must be positive, got {max_position_pct}")
    if target_risk_pct <= 0:
        return max_position_pct
    if daily_vol_pct is None or math.isnan(daily_vol_pct):
        return 0.0
    if daily_vol_pct <= 0:
        return max_position_pct
    return min(max_position_pct, target_risk_pct / daily_vol_pct * 100)


def target_shares(
    target: int,
    equity: float,
    price: float,
    max_position_pct: float,
) -> int:
    """Return the signed whole-share position for a signal target.

    Sizes to max_position_pct of equity at the given price, rounded down.
    Returns 0 when the target is flat or when even one share would breach
    the cap.

    Callers doing volatility scaling pass the narrowed budget from
    `volatility_budget_pct` here rather than the raw cap: this function only
    ever converts a percentage of equity into shares, and does not care which
    rule produced the percentage.
    """
    if target not in (-1, 0, 1):
        raise ValueError(f"target must be -1, 0, or 1, got {target}")
    if equity <= 0:
        raise ValueError(f"equity must be positive, got {equity}")
    if price <= 0:
        raise ValueError(f"price must be positive, got {price}")

    if target == 0:
        return 0

    budget = equity * max_position_pct / 100
    shares = int(budget / price)
    return target * shares
