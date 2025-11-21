"""Shared data models for the TradingEconomics calendar scraper."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(slots=True)
class CalendarRow:
    """Normalized representation of a calendar entry."""

    event_id: str
    dt_utc: Optional[datetime]
    dt_kst: Optional[datetime]
    title: str
    category: Optional[str] = None
    impact: Optional[int] = None  # 1 = low, 2 = medium, 3 = high
    country: Optional[str] = None
    raw_time_text: Optional[str] = None
    source_url: Optional[str] = None
    actual: Optional[str] = None
    previous: Optional[str] = None
    consensus: Optional[str] = None
    forecast: Optional[str] = None


