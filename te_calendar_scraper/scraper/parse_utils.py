"""Parsing helpers for TradingEconomics calendar events."""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from typing import Optional

from dateutil import parser as date_parser
from dateutil import tz
from playwright.async_api import Locator

from te_calendar_scraper import config

dt_type = datetime


def clean_text(value: Optional[str]) -> Optional[str]:
    """Normalize whitespace and strip strings."""
    if value is None:
        return None
    return " ".join(value.split()).strip() or None


async def random_delay(min_ms: int = 200, max_ms: int = 600) -> None:
    """Sleep for a random short duration to avoid hammering the site."""
    await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


def parse_time_to_utc(
    raw_text: Optional[str],
    context_datetime: Optional[datetime],
    site_tz_hint: Optional[str] = None,
) -> Optional[datetime]:
    """Parse a timestamp text into a UTC datetime when possible."""
    text = clean_text(raw_text)
    if not text:
        return None

    lowered = text.lower()
    if lowered in {"--", "n/a", "na", "all day", "all-day", "tentative"}:
        return None

    if context_datetime is None:
        return None

    site_tz_hint = site_tz_hint or config.SITE_TIMEZONE_HINT
    tzinfo = tz.gettz(site_tz_hint)
    default_dt = context_datetime
    if default_dt.tzinfo is None:
        default_dt = default_dt.replace(tzinfo=tzinfo)

    try:
        parsed = date_parser.parse(text, default=default_dt)
    except (ValueError, TypeError):
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tzinfo)

    try:
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def to_kst(dt_utc: Optional[datetime]) -> Optional[datetime]:
    """Convert UTC datetime to Asia/Seoul."""
    if dt_utc is None:
        return None
    return dt_utc.astimezone(tz.gettz(config.TZ_DISPLAY))


async def locator_text(parent: Locator, selector: Optional[str]) -> Optional[str]:
    """Retrieve text content from a nested locator if selector is provided."""
    if not selector:
        return None
    child = parent.locator(selector)
    if await child.count() == 0:
        return None
    return await child.first.text_content()


async def locator_href(parent: Locator, selector: Optional[str]) -> Optional[str]:
    """Return href attribute from nested element."""
    if not selector:
        return None
    child = parent.locator(selector)
    if await child.count() == 0:
        return None
    return await child.first.get_attribute("href")


async def extract_impact(parent: Locator, selector: Optional[str]) -> Optional[int]:
    """Derive impact level from icon count, class names, or data attributes."""
    if not selector:
        return None
    child = parent.locator(selector)
    if await child.count() == 0:
        return None
    element = child.first
    for attr in ("data-importance", "data-importance-level", "data-impact"):
        val = await element.get_attribute(attr)
        if val and val.isdigit():
            return int(val)
    classes = (await element.get_attribute("class") or "").split()
    for cls in classes:
        if cls.startswith("importance-"):
            suffix = cls.split("-", 1)[-1]
            if suffix.isdigit():
                return int(suffix)
        if cls.startswith("calendar-date-"):
            suffix = cls.split("-")[-1]
            if suffix.isdigit():
                return int(suffix)
    text = await element.text_content()
    if text and text.strip().isdigit():
        return int(text.strip())
    return None


