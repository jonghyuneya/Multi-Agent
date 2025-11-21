"""Parsing helpers for TradingEconomics calendar events."""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from typing import Iterable, Optional

from dateutil import parser as date_parser
from dateutil import tz

import config

DATE_PATTERN = "%Y-%m-%d"


def clean_text(value: Optional[str]) -> Optional[str]:
    """Normalize whitespace and strip strings."""
    if value is None:
        return None
    cleaned = " ".join(value.split()).strip()
    return cleaned or None


async def random_delay(min_ms: int = 200, max_ms: int = 600) -> None:
    """Sleep for a random short duration to avoid hammering the site."""
    await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


def extract_date_from_classes(classes: Iterable[str]) -> Optional[str]:
    """Return the first YYYY-MM-DD token found in a sequence of class names."""
    for cls in classes or []:
        token = cls.strip()
        if len(token) == 10 and token[4] == "-" and token[7] == "-":
            return token
    return None


def parse_time_to_utc(
    raw_text: Optional[str],
    date_str: Optional[str],
    site_tz_hint: str | None = None,
) -> Optional[datetime]:
    """Parse a timestamp text into a timezone-aware UTC datetime."""
    if not date_str:
        return None

    if not raw_text or not raw_text.strip():
        return None

    stripped = raw_text.strip()
    lowered = stripped.lower()
    if any(token in lowered for token in ("all day", "tentative", "tba", "na", "n/a")):
        return None

    site_tz_hint = site_tz_hint or config.SITE_TIMEZONE_HINT
    tzinfo = tz.gettz(site_tz_hint)

    try:
        base_date = datetime.strptime(date_str, DATE_PATTERN)
    except ValueError:
        return None

    default_dt = base_date.replace(tzinfo=tzinfo)
    try:
        parsed = date_parser.parse(stripped, default=default_dt)
    except (ValueError, TypeError):
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tzinfo)

    return parsed.astimezone(timezone.utc)


def to_kst(dt_utc: Optional[datetime]) -> Optional[datetime]:
    """Convert UTC datetime to Asia/Seoul."""
    if dt_utc is None:
        return None
    return dt_utc.astimezone(tz.gettz(config.TZ_DISPLAY))


def resolve_url(path: Optional[str]) -> Optional[str]:
    """Resolve relative links to absolute URLs."""
    if not path:
        return None
    path = path.strip()
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{config.BASE_URL}{path}"


def format_country(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    parts = [part.capitalize() for part in value.split()]
    return " ".join(parts)


