"""Sentiment aggregation and gating: pure math, no model, no network.

Age decay: a headline's weight halves every half_life_hours, so this
morning's story outvotes yesterday's. Whitelist: only trusted sources get a
vote. The gate can only veto entries the base signal proposes; sentiment
never creates a position on its own.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ScoredHeadline:
    ts: datetime
    source: str
    score: float


def aggregate_sentiment(
    items: list[ScoredHeadline],
    now: datetime,
    half_life_hours: float,
    source_whitelist: list[str],
) -> float | None:
    """Decay-weighted average score in [-1, +1], or None with no whitelisted news.

    None means "no information": the gate must treat it as no-veto, because
    silence about a stock is not the same as bad news about it.
    """
    allowed = {s.lower() for s in source_whitelist}
    weight_sum = 0.0
    score_sum = 0.0
    for item in items:
        if item.source.lower() not in allowed:
            continue
        age_hours = max((now - item.ts).total_seconds() / 3600, 0.0)
        weight = 0.5 ** (age_hours / half_life_hours)
        weight_sum += weight
        score_sum += weight * item.score
    if weight_sum == 0.0:
        return None
    return score_sum / weight_sum


def apply_sentiment_gate(target: int, score: float | None, threshold: float) -> tuple[int, str]:
    """Veto a long on decisively negative news, a short on decisively positive.

    Returns (possibly overridden target, reason). Reason is empty when the
    gate did not act.
    """
    if score is None:
        return target, ""
    if target == 1 and score <= -threshold:
        return 0, f"long gated: sentiment {score:+.2f} <= -{threshold:.2f}"
    if target == -1 and score >= threshold:
        return 0, f"short gated: sentiment {score:+.2f} >= +{threshold:.2f}"
    return target, ""
