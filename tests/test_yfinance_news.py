from datetime import datetime, timezone

from diyquant.data.providers.yfinance_news import parse_item


def raw_item(**overrides) -> dict:
    content = {
        "title": "Apple reports record profit",
        "pubDate": "2026-07-19T14:30:00Z",
        "provider": {"displayName": "Reuters"},
        "canonicalUrl": {"url": "https://example.com/story"},
    }
    content.update(overrides)
    return {"content": content}


def test_parses_complete_item():
    item = parse_item(raw_item())
    assert item.headline == "Apple reports record profit"
    assert item.source == "Reuters"
    assert item.url == "https://example.com/story"
    assert item.ts == datetime(2026, 7, 19, 14, 30, tzinfo=timezone.utc)


def test_missing_title_returns_none():
    assert parse_item(raw_item(title=None)) is None


def test_missing_pubdate_returns_none():
    assert parse_item(raw_item(pubDate=None)) is None


def test_malformed_date_returns_none():
    assert parse_item(raw_item(pubDate="not-a-date")) is None


def test_missing_provider_defaults_to_empty_source():
    assert parse_item(raw_item(provider=None)).source == ""
