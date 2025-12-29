"""Optional keyword-based event filter helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional


@dataclass
class EventBucket:
    name: str
    keywords: List[str]


DEFAULT_BUCKETS = [
    EventBucket("CPI", ["inflation", "cpi", "consumer price"]),
    EventBucket("EIA", ["eia", "crude", "inventory", "gas", "petroleum"]),
    EventBucket("ISM", ["ism", "manufacturing", "services"]),
    EventBucket("FOMC", ["fomc", "fed", "federal reserve"]),
    EventBucket("Bonds", ["auction", "treasury", "bond", "note", "bill"]),
]


def assign_buckets(
    title: str,
    buckets: Iterable[EventBucket] = DEFAULT_BUCKETS,
) -> List[str]:
    """Return a list of bucket names the title belongs to."""
    title_lower = (title or "").lower()
    matches = [
        bucket.name
        for bucket in buckets
        if any(keyword in title_lower for keyword in bucket.keywords)
    ]
    return matches


