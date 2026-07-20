from datetime import datetime, timedelta, timezone

from diyquant.signals.sentiment.filter import (
    ScoredHeadline,
    aggregate_sentiment,
    apply_sentiment_gate,
)

NOW = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)


def item(hours_ago: float, score: float, source: str = "benzinga") -> ScoredHeadline:
    return ScoredHeadline(ts=NOW - timedelta(hours=hours_ago), source=source, score=score)


def test_no_news_returns_none():
    assert aggregate_sentiment([], NOW, half_life_hours=24, source_whitelist=["benzinga"]) is None


def test_non_whitelisted_sources_do_not_vote():
    items = [item(1, -0.9, source="randomblog")]
    assert aggregate_sentiment(items, NOW, 24, ["benzinga"]) is None


def test_whitelist_is_case_insensitive():
    items = [item(1, 0.5, source="Benzinga")]
    assert aggregate_sentiment(items, NOW, 24, ["benzinga"]) == 0.5


def test_fresh_news_outvotes_stale_news():
    items = [item(0, 1.0), item(48, -1.0)]
    score = aggregate_sentiment(items, NOW, half_life_hours=24, source_whitelist=["benzinga"])
    # 48h old at 24h half-life carries 1/4 the weight: (1.0 - 0.25) / 1.25
    assert score == (1.0 - 0.25) / 1.25


def test_equal_age_items_average():
    items = [item(2, 0.6), item(2, -0.2)]
    score = aggregate_sentiment(items, NOW, 24, ["benzinga"])
    assert abs(score - 0.2) < 1e-9


def test_gate_blocks_long_on_negative_news():
    target, reason = apply_sentiment_gate(target=1, score=-0.5, threshold=0.2)
    assert target == 0
    assert "long gated" in reason


def test_gate_blocks_short_on_positive_news():
    target, reason = apply_sentiment_gate(target=-1, score=0.5, threshold=0.2)
    assert target == 0
    assert "short gated" in reason


def test_gate_passes_long_on_mild_negative():
    target, reason = apply_sentiment_gate(target=1, score=-0.1, threshold=0.2)
    assert target == 1
    assert reason == ""


def test_gate_ignores_missing_score():
    assert apply_sentiment_gate(target=1, score=None, threshold=0.2) == (1, "")


def test_gate_never_touches_flat_target():
    assert apply_sentiment_gate(target=0, score=-0.9, threshold=0.2) == (0, "")
