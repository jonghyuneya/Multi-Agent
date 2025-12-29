"""CSV output helpers for TradingEconomics calendar data."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, List

import pandas as pd

from te_calendar_scraper import config
from te_calendar_scraper.io import dedupe


def _ensure_iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def prepare_rows_for_csv(rows: Iterable[dict]) -> List[dict]:
    cleaned: List[dict] = []
    for row in rows:
        cleaned.append(
            {
                **row,
                "datetime_kst": _ensure_iso(row.get("datetime_kst")),
                "datetime_utc": _ensure_iso(row.get("datetime_utc")),
            }
        )
    return cleaned


def save_calendar_csv(rows: Iterable[dict], start_date, end_date) -> Path:
    """Save calendar rows to a CSV file within the project output directory."""
    unique_rows = dedupe.dedupe_by_key(rows, keys=("datetime_kst", "title", "source_url"))
    prepared_rows = prepare_rows_for_csv(unique_rows)
    if not prepared_rows:
        raise RuntimeError("No rows to save.")

    df = pd.DataFrame(prepared_rows)
    df.sort_values(by=["datetime_kst", "title"], inplace=True, ignore_index=True)

    file_name = f"calendar_US_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.csv"
    output_path = config.CALENDAR_OUTPUT_DIR / file_name
    df.to_csv(output_path, index=False)
    return output_path


def save_indicators_csv(rows: Iterable[dict], as_of_date: date) -> Path:
    """Persist indicator headline data."""

    prepared = [
        {
            "indicator_bucket": row.get("indicator_bucket"),
            "indicator_name": row.get("indicator_name"),
            "latest_value": row.get("latest_value") or "",
            "unit": row.get("unit") or "",
            "day_change": row.get("day_change") or "",
            "month_change": row.get("month_change") or "",
            "year_change": row.get("year_change") or "",
            "obs_date": row.get("obs_date") or "",
            "source_url": row.get("source_url") or "",
            "raw_source_note": row.get("raw_source_note") or "",
        }
        for row in rows
    ]

    df = pd.DataFrame(prepared)
    df.sort_values(by=["indicator_bucket", "indicator_name"], inplace=True, ignore_index=True)

    file_name = f"indicators_US_{as_of_date.strftime('%Y%m%d')}.csv"
    output_path = config.INDICATOR_OUTPUT_DIR / file_name
    df.to_csv(output_path, index=False)
    return output_path


