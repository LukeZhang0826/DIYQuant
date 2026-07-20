"""Shared data models."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NewsItem:
    ts: datetime
    source: str
    headline: str
    url: str
