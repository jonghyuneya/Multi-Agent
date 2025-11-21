"""Shared data models for the TradingEconomics calendar scraper."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(slots=True)
class CalendarRow:
    """Normalised representation of a calendar entry."""

    dt_utc: Optional[datetime]
    dt_kst: Optional[datetime]
    title: str
    category: Optional[str] = None
    impact: Optional[int] = None
    country: Optional[str] = None
    raw_time_text: Optional[str] = None
    source_url: Optional[str] = None


@dataclass(slots=True)
class IndicatorRow:
    """Normalised representation of an indicator headline value."""

    indicator_bucket: str
    indicator_name: str
    latest_value: Optional[str]
    unit: Optional[str]
    day_change: Optional[str]
    month_change: Optional[str]
    year_change: Optional[str]
    obs_date: Optional[str]
    source_url: Optional[str]
    raw_source_note: Optional[str]


