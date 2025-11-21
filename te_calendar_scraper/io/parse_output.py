"""Parser for output calendar and indicator CSV files."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from te_calendar_scraper import config

logger = logging.getLogger(__name__)


def parse_calendar_csv(file_path: Optional[Path] = None) -> pd.DataFrame:
    """Parse a calendar CSV file.
    
    Args:
        file_path: Path to the calendar CSV file. If None, finds the most recent one.
        
    Returns:
        DataFrame with calendar data.
    """
    if file_path is None:
        # Find the most recent calendar CSV file
        calendar_files = sorted(
            config.CALENDAR_OUTPUT_DIR.glob("calendar_US_*.csv"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        if not calendar_files:
            raise FileNotFoundError("No calendar CSV files found in calendar output directory")
        file_path = calendar_files[0]
        logger.info(f"Using most recent calendar file: {file_path.name}")
    
    if not file_path.exists():
        raise FileNotFoundError(f"Calendar file not found: {file_path}")
    
    df = pd.read_csv(file_path)
    
    # Parse datetime columns
    if "datetime_utc" in df.columns:
        df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True)
    if "datetime_kst" in df.columns:
        df["datetime_kst"] = pd.to_datetime(df["datetime_kst"])
    
    logger.info(f"Parsed {len(df)} calendar entries from {file_path.name}")
    return df


def parse_indicator_csv(file_path: Optional[Path] = None) -> pd.DataFrame:
    """Parse an indicator CSV file.
    
    Args:
        file_path: Path to the indicator CSV file. If None, finds the most recent one.
        
    Returns:
        DataFrame with indicator data.
    """
    if file_path is None:
        # Find the most recent indicator CSV file
        indicator_files = sorted(
            config.INDICATOR_OUTPUT_DIR.glob("indicators_US_*.csv"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        if not indicator_files:
            raise FileNotFoundError("No indicator CSV files found in indicator output directory")
        file_path = indicator_files[0]
        logger.info(f"Using most recent indicator file: {file_path.name}")
    
    if not file_path.exists():
        raise FileNotFoundError(f"Indicator file not found: {file_path}")
    
    df = pd.read_csv(file_path)
    
    # Parse date column if it exists
    if "obs_date" in df.columns:
        df["obs_date"] = pd.to_datetime(df["obs_date"], errors="coerce")
    
    logger.info(f"Parsed {len(df)} indicators from {file_path.name}")
    return df


def list_calendar_files() -> list[Path]:
    """List all calendar CSV files in the calendar output directory.
    
    Returns:
        List of calendar CSV file paths, sorted by modification time (newest first).
    """
    files = sorted(
        config.CALENDAR_OUTPUT_DIR.glob("calendar_US_*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    return files


def list_indicator_files() -> list[Path]:
    """List all indicator CSV files in the indicator output directory.
    
    Returns:
        List of indicator CSV file paths, sorted by modification time (newest first).
    """
    files = sorted(
        config.INDICATOR_OUTPUT_DIR.glob("indicators_US_*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    return files


def get_calendar_summary(df: pd.DataFrame) -> dict:
    """Get summary statistics from a calendar DataFrame.
    
    Args:
        df: Calendar DataFrame.
        
    Returns:
        Dictionary with summary statistics.
    """
    summary = {
        "total_entries": len(df),
        "date_range": None,
        "categories": {},
        "impact_distribution": {},
        "countries": set(),
    }
    
    if "datetime_kst" in df.columns and len(df) > 0:
        summary["date_range"] = {
            "start": df["datetime_kst"].min(),
            "end": df["datetime_kst"].max(),
        }
    
    if "category" in df.columns:
        summary["categories"] = df["category"].value_counts().to_dict()
    
    if "impact" in df.columns:
        summary["impact_distribution"] = df["impact"].value_counts().to_dict()
    
    if "country" in df.columns:
        summary["countries"] = set(df["country"].dropna().unique())
    
    return summary


def get_indicator_summary(df: pd.DataFrame) -> dict:
    """Get summary statistics from an indicator DataFrame.
    
    Args:
        df: Indicator DataFrame.
        
    Returns:
        Dictionary with summary statistics.
    """
    summary = {
        "total_indicators": len(df),
        "buckets": {},
        "date_range": None,
    }
    
    if "indicator_bucket" in df.columns:
        summary["buckets"] = df["indicator_bucket"].value_counts().to_dict()
    
    if "obs_date" in df.columns and len(df) > 0:
        valid_dates = df["obs_date"].dropna()
        if len(valid_dates) > 0:
            summary["date_range"] = {
                "start": valid_dates.min(),
                "end": valid_dates.max(),
            }
    
    return summary

