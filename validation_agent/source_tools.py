"""
Source tools for the Validation Agent.

This module provides concrete implementations of SourceTool for various data sources.
Each tool knows how to:
1. Load data from its source (CSV, JSON, PDF, etc.)
2. Search for specific data
3. Validate claims against source data

To add a new source type:
1. Create a new class that inherits from SourceTool
2. Implement all required methods
3. Register with ValidationAgent

Example:
    class MyNewSourceTool(SourceTool):
        @property
        def source_type(self) -> str:
            return "my_source"
        
        def load_sources(self, path: Path) -> None:
            # Your loading logic
            pass
        
        def search(self, query: str) -> List[Dict[str, Any]]:
            # Your search logic
            pass
        
        def validate_claim(self, claim: str, reference: str) -> SourceMatch:
            # Your validation logic
            pass
"""

from __future__ import annotations

import csv
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from validation_agent.base import (
    SourceTool,
    SourceMatch,
    ValidationStatus,
)

logger = logging.getLogger(__name__)


# =============================================================================
# TradingEconomics Calendar Source Tool
# =============================================================================

class TECalendarSourceTool(SourceTool):
    """
    Source tool for TradingEconomics calendar data.
    
    Loads and validates against calendar CSV files from te_calendar_scraper.
    
    Expected CSV columns:
    - datetime_utc, datetime_kst, title, category, impact, country, raw_time_text, source_url
    """
    
    def __init__(self):
        self._data: List[Dict[str, Any]] = []
        self._loaded: bool = False
    
    @property
    def source_type(self) -> str:
        return "calendar_events"
    
    def load_sources(self, path: Path) -> None:
        """Load calendar CSV files from the given path."""
        self._data = []
        
        if path.is_file() and path.suffix == ".csv":
            self._load_csv(path)
        elif path.is_dir():
            # Load all calendar CSV files
            for csv_file in sorted(path.glob("calendar_*.csv")):
                self._load_csv(csv_file)
        
        self._loaded = True
        logger.info(f"Loaded {len(self._data)} calendar events")
    
    def _load_csv(self, path: Path) -> None:
        """Load a single CSV file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self._data.append({
                        "datetime_utc": row.get("datetime_utc", ""),
                        "datetime_kst": row.get("datetime_kst", ""),
                        "title": row.get("title", ""),
                        "category": row.get("category", ""),
                        "impact": row.get("impact", ""),
                        "country": row.get("country", ""),
                        "raw_time_text": row.get("raw_time_text", ""),
                        "source_url": row.get("source_url", ""),
                        "_source_file": path.name,
                    })
        except Exception as e:
            logger.error(f"Error loading {path}: {e}")
    
    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search calendar events by title, category, or date."""
        if not self._loaded:
            return []
        
        query_lower = query.lower()
        results = []
        
        for event in self._data:
            # Search in title
            if query_lower in event.get("title", "").lower():
                results.append(event)
                continue
            
            # Search in category
            if query_lower in event.get("category", "").lower():
                results.append(event)
                continue
            
            # Search in date
            if query in event.get("datetime_utc", "") or query in event.get("datetime_kst", ""):
                results.append(event)
                continue
        
        return results
    
    def validate_claim(self, claim: str, reference: str) -> SourceMatch:
        """
        Validate a calendar-related claim.
        
        Reference format expected: "Event Name, YYYY-MM-DD" or similar
        """
        if not self._loaded:
            return SourceMatch(
                claim=claim,
                source_type=self.source_type,
                source_reference=reference,
                status=ValidationStatus.ERROR,
                explanation="Calendar data not loaded"
            )
        
        # Parse reference to extract event name and date
        # Expected formats:
        # - "FOMC Interest Rate Decision, 2025-12-11"
        # - "CPI YoY, 2025-12-10, 08:30 AM"
        
        parts = [p.strip() for p in reference.split(",")]
        event_name = parts[0] if parts else ""
        event_date = parts[1] if len(parts) > 1 else ""
        
        # Search for matching event
        matches = []
        for event in self._data:
            title_match = event_name.lower() in event.get("title", "").lower()
            date_match = event_date in event.get("datetime_utc", "") or event_date in event.get("datetime_kst", "")
            
            if title_match and (not event_date or date_match):
                matches.append(event)
        
        if not matches:
            return SourceMatch(
                claim=claim,
                source_type=self.source_type,
                source_reference=reference,
                status=ValidationStatus.NOT_FOUND,
                explanation=f"No matching event found for: {reference}"
            )
        
        # Found match - validate details
        best_match = matches[0]
        
        return SourceMatch(
            claim=claim,
            source_type=self.source_type,
            source_reference=reference,
            source_data=best_match,
            status=ValidationStatus.VALID,
            confidence=0.9 if len(matches) == 1 else 0.7,
            explanation=f"Matched event: {best_match.get('title')} on {best_match.get('datetime_kst')}"
        )
    
    def get_tool_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "search_calendar_events",
                "description": "Search economic calendar events by title, category, or date. Use this to verify calendar-related claims.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (event name, category, or date like 'FOMC', 'CPI', '2025-12-11')"
                        },
                        "date": {
                            "type": "string",
                            "description": "Optional: Filter by date (YYYY-MM-DD format)"
                        }
                    },
                    "required": ["query"]
                }
            }
        }


# =============================================================================
# TradingEconomics Indicators Source Tool
# =============================================================================

class TEIndicatorsSourceTool(SourceTool):
    """
    Source tool for TradingEconomics indicator data.
    
    Loads and validates against indicator CSV files from te_calendar_scraper.
    
    Expected CSV columns:
    - indicator_bucket, indicator_name, latest_value, unit, day_change, 
      month_change, year_change, obs_date, source_url, raw_source_note
    """
    
    def __init__(self):
        self._data: List[Dict[str, Any]] = []
        self._loaded: bool = False
    
    @property
    def source_type(self) -> str:
        return "macro_data"
    
    def load_sources(self, path: Path) -> None:
        """Load indicator CSV files from the given path."""
        self._data = []
        
        if path.is_file() and path.suffix == ".csv":
            self._load_csv(path)
        elif path.is_dir():
            # Load most recent indicator file
            csv_files = sorted(path.glob("indicators_*.csv"), reverse=True)
            if csv_files:
                self._load_csv(csv_files[0])
        
        self._loaded = True
        logger.info(f"Loaded {len(self._data)} indicators")
    
    def _load_csv(self, path: Path) -> None:
        """Load a single CSV file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self._data.append({
                        "indicator_bucket": row.get("indicator_bucket", ""),
                        "indicator_name": row.get("indicator_name", ""),
                        "latest_value": row.get("latest_value", ""),
                        "unit": row.get("unit", ""),
                        "day_change": row.get("day_change", ""),
                        "month_change": row.get("month_change", ""),
                        "year_change": row.get("year_change", ""),
                        "obs_date": row.get("obs_date", ""),
                        "source_url": row.get("source_url", ""),
                        "_source_file": path.name,
                    })
        except Exception as e:
            logger.error(f"Error loading {path}: {e}")
    
    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search indicators by name or bucket."""
        if not self._loaded:
            return []
        
        query_lower = query.lower()
        results = []
        
        for indicator in self._data:
            # Search in name
            if query_lower in indicator.get("indicator_name", "").lower():
                results.append(indicator)
                continue
            
            # Search in bucket
            if query_lower in indicator.get("indicator_bucket", "").lower():
                results.append(indicator)
                continue
        
        return results
    
    def validate_claim(self, claim: str, reference: str) -> SourceMatch:
        """
        Validate an indicator-related claim.
        
        Reference format expected: "Indicator Name: Value[Unit], Date"
        Examples:
        - "US 10Y Yield: 4.08%, 2025-11-13"
        - "CPI YoY: 3.0percent, 2025-09-01"
        """
        if not self._loaded:
            return SourceMatch(
                claim=claim,
                source_type=self.source_type,
                source_reference=reference,
                status=ValidationStatus.ERROR,
                explanation="Indicator data not loaded"
            )
        
        # Parse reference
        # Format: "Indicator Name: Value[Unit], Date" or "Indicator Name: Value"
        match = re.match(r"([^:]+):\s*([^,]+)(?:,\s*(.+))?", reference)
        
        if not match:
            return SourceMatch(
                claim=claim,
                source_type=self.source_type,
                source_reference=reference,
                status=ValidationStatus.ERROR,
                explanation=f"Could not parse reference format: {reference}"
            )
        
        indicator_name = match.group(1).strip()
        claimed_value = match.group(2).strip()
        claimed_date = match.group(3).strip() if match.group(3) else None
        
        # Search for matching indicator
        matches = []
        for indicator in self._data:
            if indicator_name.lower() in indicator.get("indicator_name", "").lower():
                matches.append(indicator)
        
        if not matches:
            return SourceMatch(
                claim=claim,
                source_type=self.source_type,
                source_reference=reference,
                status=ValidationStatus.NOT_FOUND,
                explanation=f"No matching indicator found for: {indicator_name}"
            )
        
        # Validate value
        best_match = matches[0]
        source_value = best_match.get("latest_value", "")
        source_unit = best_match.get("unit", "")
        
        # Normalize values for comparison
        claimed_normalized = re.sub(r"[^\d.]", "", claimed_value)
        source_normalized = re.sub(r"[^\d.]", "", source_value)
        
        if claimed_normalized == source_normalized:
            return SourceMatch(
                claim=claim,
                source_type=self.source_type,
                source_reference=reference,
                source_data=best_match,
                status=ValidationStatus.VALID,
                confidence=0.95,
                explanation=f"Value matches: {source_value}{source_unit}"
            )
        else:
            return SourceMatch(
                claim=claim,
                source_type=self.source_type,
                source_reference=reference,
                source_data=best_match,
                status=ValidationStatus.INVALID,
                confidence=0.8,
                explanation=f"Value mismatch: claimed {claimed_value}, source has {source_value}{source_unit}",
                suggested_correction=f"{indicator_name}: {source_value}{source_unit}"
            )
    
    def get_tool_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "search_macro_data",
                "description": "Search macroeconomic indicators (CPI, PMI, yields, etc.) to verify indicator-related claims.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (indicator name like 'CPI', 'US 10Y Yield', 'ISM Manufacturing')"
                        },
                        "bucket": {
                            "type": "string",
                            "description": "Optional: Filter by bucket (CPI, UST, ISM, EIA)"
                        }
                    },
                    "required": ["query"]
                }
            }
        }


# =============================================================================
# FOMC Source Tool
# =============================================================================

class FOMCSourceTool(SourceTool):
    """
    Source tool for FOMC press conference data.
    
    Loads metadata about downloaded FOMC PDFs.
    For full text validation, would need PDF parsing (not implemented).
    """
    
    def __init__(self):
        self._data: List[Dict[str, Any]] = []
        self._loaded: bool = False
    
    @property
    def source_type(self) -> str:
        return "fomc_events"
    
    def load_sources(self, path: Path) -> None:
        """Load FOMC PDF metadata from the given directory."""
        self._data = []
        
        if not path.is_dir():
            logger.warning(f"FOMC path is not a directory: {path}")
            return
        
        # Parse PDF filenames to extract metadata
        # Format: {year}_{month}_{dates}_press_conference.pdf
        for pdf_file in path.glob("*.pdf"):
            filename = pdf_file.stem
            parts = filename.split("_")
            
            if len(parts) >= 3:
                year = parts[0]
                month = parts[1]
                dates = parts[2]
                
                self._data.append({
                    "year": year,
                    "month": month,
                    "dates": dates,
                    "title": f"FOMC Press Conference - {month.capitalize()} {year}",
                    "filename": pdf_file.name,
                    "path": str(pdf_file),
                    "_source_file": pdf_file.name,
                })
        
        self._loaded = True
        logger.info(f"Loaded {len(self._data)} FOMC documents")
    
    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search FOMC documents by date or title."""
        if not self._loaded:
            return []
        
        query_lower = query.lower()
        results = []
        
        for doc in self._data:
            # Search in title
            if query_lower in doc.get("title", "").lower():
                results.append(doc)
                continue
            
            # Search in year/month
            if query in doc.get("year", "") or query_lower in doc.get("month", "").lower():
                results.append(doc)
                continue
        
        return results
    
    def validate_claim(self, claim: str, reference: str) -> SourceMatch:
        """
        Validate an FOMC-related claim.
        
        Note: This validates that the FOMC document exists, not the content.
        Full content validation would require PDF parsing.
        """
        if not self._loaded:
            return SourceMatch(
                claim=claim,
                source_type=self.source_type,
                source_reference=reference,
                status=ValidationStatus.ERROR,
                explanation="FOMC data not loaded"
            )
        
        # Search for matching document
        matches = self.search(reference)
        
        if not matches:
            return SourceMatch(
                claim=claim,
                source_type=self.source_type,
                source_reference=reference,
                status=ValidationStatus.NOT_FOUND,
                explanation=f"No matching FOMC document found for: {reference}"
            )
        
        best_match = matches[0]
        
        return SourceMatch(
            claim=claim,
            source_type=self.source_type,
            source_reference=reference,
            source_data=best_match,
            status=ValidationStatus.PARTIAL,  # Partial because we can't verify content
            confidence=0.6,
            explanation=f"FOMC document exists: {best_match.get('filename')}. Content validation requires PDF parsing."
        )
    
    def get_tool_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "search_fomc_events",
                "description": "Search FOMC press conference documents to verify FOMC-related claims.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (year, month, or title like '2024', 'December', 'FOMC Press Conference')"
                        }
                    },
                    "required": ["query"]
                }
            }
        }


# =============================================================================
# News Source Tool
# =============================================================================

class NewsSourceTool(SourceTool):
    """
    Source tool for news articles.
    
    Can load news from:
    - JSON files
    - DynamoDB (if configured)
    
    This is a template - customize for your news source.
    """
    
    def __init__(self):
        self._data: List[Dict[str, Any]] = []
        self._loaded: bool = False
    
    @property
    def source_type(self) -> str:
        return "news_data"
    
    def load_sources(self, path: Path) -> None:
        """Load news data from JSON files."""
        self._data = []
        
        if path.is_file() and path.suffix == ".json":
            self._load_json(path)
        elif path.is_dir():
            for json_file in path.glob("*.json"):
                self._load_json(json_file)
        
        self._loaded = True
        logger.info(f"Loaded {len(self._data)} news articles")
    
    def _load_json(self, path: Path) -> None:
        """Load a single JSON file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        item["_source_file"] = path.name
                        self._data.append(item)
                elif isinstance(data, dict):
                    data["_source_file"] = path.name
                    self._data.append(data)
        except Exception as e:
            logger.error(f"Error loading {path}: {e}")
    
    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search news articles by headline, provider, or content."""
        if not self._loaded:
            return []
        
        query_lower = query.lower()
        results = []
        
        for article in self._data:
            # Search in headline/title
            headline = article.get("headline", "") or article.get("title", "")
            if query_lower in headline.lower():
                results.append(article)
                continue
            
            # Search in provider/source
            provider = article.get("provider", "") or article.get("source", "")
            if query_lower in provider.lower():
                results.append(article)
                continue
            
            # Search in summary
            summary = article.get("summary", "")
            if query_lower in summary.lower():
                results.append(article)
                continue
        
        return results
    
    def validate_claim(self, claim: str, reference: str) -> SourceMatch:
        """
        Validate a news-related claim.
        
        Reference format expected: '"Headline" - Provider'
        """
        if not self._loaded:
            return SourceMatch(
                claim=claim,
                source_type=self.source_type,
                source_reference=reference,
                status=ValidationStatus.ERROR,
                explanation="News data not loaded"
            )
        
        # Parse reference
        # Format: '"Headline" - Provider' or just 'Headline'
        match = re.match(r'"([^"]+)"(?:\s*-\s*(.+))?', reference)
        
        if match:
            headline = match.group(1).strip()
            provider = match.group(2).strip() if match.group(2) else None
        else:
            headline = reference.strip()
            provider = None
        
        # Search for matching article
        matches = []
        for article in self._data:
            article_headline = article.get("headline", "") or article.get("title", "")
            article_provider = article.get("provider", "") or article.get("source", "")
            
            # Check headline match (fuzzy)
            if headline.lower() in article_headline.lower() or article_headline.lower() in headline.lower():
                if provider is None or provider.lower() in article_provider.lower():
                    matches.append(article)
        
        if not matches:
            return SourceMatch(
                claim=claim,
                source_type=self.source_type,
                source_reference=reference,
                status=ValidationStatus.NOT_FOUND,
                explanation=f"No matching news article found for: {headline}"
            )
        
        best_match = matches[0]
        
        return SourceMatch(
            claim=claim,
            source_type=self.source_type,
            source_reference=reference,
            source_data=best_match,
            status=ValidationStatus.VALID,
            confidence=0.85,
            explanation=f"Matched article: {best_match.get('headline', best_match.get('title'))}"
        )
    
    def get_tool_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "search_news_data",
                "description": "Search news articles by headline, provider, or content to verify news-related claims.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (headline keywords, provider name like 'Reuters', 'Bloomberg')"
                        },
                        "provider": {
                            "type": "string",
                            "description": "Optional: Filter by news provider"
                        }
                    },
                    "required": ["query"]
                }
            }
        }


# =============================================================================
# Template for Custom Source Tools
# =============================================================================

# =============================================================================
# Briefing Script Source Tool (for structured script JSON with embedded sources)
# =============================================================================

class BriefingScriptSourceTool(SourceTool):
    """
    Source tool for validating briefing scripts with embedded source references.
    
    This tool handles scripts in the structured JSON format with sources like:
    - type: "article" (news articles with pk, title)
    - type: "chart" (market data with ticker, date range)
    - type: "event" (calendar events with id, title, date)
    
    It connects to external source tools for actual validation:
    - ArticleSourceTool for news articles (DynamoDB/JSON)
    - ChartDataSourceTool for market data (Yahoo Finance, etc.)
    - EventSourceTool for calendar events
    
    Script JSON Schema:
    {
        "date": "20251222",
        "nutshell": "요약",
        "chapter": [...],
        "scripts": [
            {
                "id": 0,
                "speaker": "진행자|해설자",
                "text": "스크립트 내용",
                "sources": [
                    {"type": "article", "pk": "id#xxx", "title": "..."},
                    {"type": "chart", "ticker": "^GSPC", "start_date": "...", "end_date": "..."},
                    {"type": "event", "id": "123", "title": "...", "date": "..."}
                ],
                "time": [start_ms, end_ms]
            }
        ]
    }
    """
    
    def __init__(self):
        self._scripts: List[Dict[str, Any]] = []
        self._articles: Dict[str, Dict[str, Any]] = {}  # pk -> article data
        self._charts: Dict[str, Dict[str, Any]] = {}     # ticker -> chart data
        self._events: Dict[str, Dict[str, Any]] = {}     # id -> event data
        self._loaded: bool = False
    
    @property
    def source_type(self) -> str:
        return "briefing_script"
    
    def load_sources(self, path: Path) -> None:
        """
        Load source data for validation.
        
        The path can be:
        - A directory containing articles.json, charts.json, events.json
        - Or individual source files will be loaded as they are registered
        """
        if path.is_dir():
            # Load articles
            articles_file = path / "articles.json"
            if articles_file.exists():
                self._load_articles(articles_file)
            
            # Load events
            events_file = path / "events.json"
            if events_file.exists():
                self._load_events(events_file)
            
            # Load charts (if pre-cached)
            charts_file = path / "charts.json"
            if charts_file.exists():
                self._load_charts(charts_file)
        
        self._loaded = True
        logger.info(f"BriefingScriptSourceTool loaded: {len(self._articles)} articles, "
                   f"{len(self._events)} events, {len(self._charts)} charts")
    
    def _load_articles(self, path: Path) -> None:
        """Load article data from JSON."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for article in data:
                        pk = article.get("pk") or article.get("id", "")
                        self._articles[pk] = article
                elif isinstance(data, dict):
                    # Could be a map of pk -> article
                    self._articles.update(data)
        except Exception as e:
            logger.error(f"Error loading articles from {path}: {e}")
    
    def _load_events(self, path: Path) -> None:
        """Load event data from JSON."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for event in data:
                        event_id = str(event.get("id", ""))
                        self._events[event_id] = event
                elif isinstance(data, dict):
                    self._events.update(data)
        except Exception as e:
            logger.error(f"Error loading events from {path}: {e}")
    
    def _load_charts(self, path: Path) -> None:
        """Load pre-cached chart data from JSON."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self._charts.update(data)
        except Exception as e:
            logger.error(f"Error loading charts from {path}: {e}")
    
    def add_articles(self, articles: List[Dict[str, Any]]) -> None:
        """Add articles to the source (for dynamic loading from DynamoDB)."""
        for article in articles:
            pk = article.get("pk") or article.get("id", "")
            self._articles[pk] = article
    
    def add_events(self, events: List[Dict[str, Any]]) -> None:
        """Add events to the source."""
        for event in events:
            event_id = str(event.get("id", ""))
            self._events[event_id] = event
    
    def add_charts(self, charts: Dict[str, Dict[str, Any]]) -> None:
        """Add chart data to the source."""
        self._charts.update(charts)
    
    def search(self, query: str) -> List[Dict[str, Any]]:
        """
        Search across all source types.
        
        Query format:
        - "article:pk#xxx" - Search for specific article by pk
        - "article:title:..." - Search articles by title
        - "chart:TICKER" - Search for chart data
        - "event:id:123" - Search for event by id
        - "event:title:..." - Search events by title
        """
        results = []
        query_lower = query.lower()
        
        # Parse query type
        if query.startswith("article:"):
            query_part = query[8:]
            if query_part.startswith("pk#") or query_part.startswith("id#"):
                # Exact pk lookup
                pk = query_part
                if pk in self._articles:
                    results.append({"type": "article", **self._articles[pk]})
            else:
                # Title search
                for pk, article in self._articles.items():
                    title = article.get("title", "")
                    if query_part.lower() in title.lower():
                        results.append({"type": "article", "pk": pk, **article})
        
        elif query.startswith("chart:"):
            ticker = query[6:].upper()
            if ticker in self._charts:
                results.append({"type": "chart", "ticker": ticker, **self._charts[ticker]})
        
        elif query.startswith("event:"):
            query_part = query[6:]
            if query_part.startswith("id:"):
                event_id = query_part[3:]
                if event_id in self._events:
                    results.append({"type": "event", "id": event_id, **self._events[event_id]})
            else:
                # Title search
                for event_id, event in self._events.items():
                    title = event.get("title", "")
                    if query_part.lower() in title.lower():
                        results.append({"type": "event", "id": event_id, **event})
        
        else:
            # General search across all
            for pk, article in self._articles.items():
                title = article.get("title", "")
                if query_lower in title.lower():
                    results.append({"type": "article", "pk": pk, **article})
            
            for event_id, event in self._events.items():
                title = event.get("title", "")
                if query_lower in title.lower():
                    results.append({"type": "event", "id": event_id, **event})
        
        return results
    
    def validate_claim(self, claim: str, reference: str) -> SourceMatch:
        """
        Validate a claim against its source reference.
        
        Reference is expected to be a JSON string of the source object:
        {"type": "article", "pk": "id#xxx", "title": "..."}
        """
        try:
            source_ref = json.loads(reference)
        except json.JSONDecodeError:
            return SourceMatch(
                claim=claim,
                source_type=self.source_type,
                source_reference=reference,
                status=ValidationStatus.ERROR,
                explanation=f"Could not parse source reference as JSON: {reference[:100]}"
            )
        
        source_type = source_ref.get("type", "")
        
        if source_type == "article":
            return self._validate_article(claim, source_ref)
        elif source_type == "chart":
            return self._validate_chart(claim, source_ref)
        elif source_type == "event":
            return self._validate_event(claim, source_ref)
        else:
            return SourceMatch(
                claim=claim,
                source_type=self.source_type,
                source_reference=reference,
                status=ValidationStatus.ERROR,
                explanation=f"Unknown source type: {source_type}"
            )
    
    def _validate_article(self, claim: str, source_ref: Dict) -> SourceMatch:
        """Validate an article source reference."""
        pk = source_ref.get("pk", "")
        title = source_ref.get("title", "")
        
        if pk in self._articles:
            article = self._articles[pk]
            article_title = article.get("title", "")
            
            # Check if title matches
            if title.lower() == article_title.lower():
                return SourceMatch(
                    claim=claim,
                    source_type="article",
                    source_reference=json.dumps(source_ref, ensure_ascii=False),
                    source_data=article,
                    status=ValidationStatus.VALID,
                    confidence=0.95,
                    explanation=f"Article verified: {article_title[:80]}"
                )
            else:
                return SourceMatch(
                    claim=claim,
                    source_type="article",
                    source_reference=json.dumps(source_ref, ensure_ascii=False),
                    source_data=article,
                    status=ValidationStatus.PARTIAL,
                    confidence=0.7,
                    explanation=f"Article found but title differs. Expected: {title[:50]}, Got: {article_title[:50]}"
                )
        else:
            return SourceMatch(
                claim=claim,
                source_type="article",
                source_reference=json.dumps(source_ref, ensure_ascii=False),
                status=ValidationStatus.NOT_FOUND,
                explanation=f"Article not found: pk={pk}"
            )
    
    def _validate_chart(self, claim: str, source_ref: Dict) -> SourceMatch:
        """Validate a chart source reference."""
        ticker = source_ref.get("ticker", "")
        start_date = source_ref.get("start_date", "")
        end_date = source_ref.get("end_date", "")
        
        if ticker in self._charts:
            chart_data = self._charts[ticker]
            
            return SourceMatch(
                claim=claim,
                source_type="chart",
                source_reference=json.dumps(source_ref, ensure_ascii=False),
                source_data=chart_data,
                status=ValidationStatus.VALID,
                confidence=0.9,
                explanation=f"Chart data available for {ticker} ({start_date} to {end_date})"
            )
        else:
            # Chart data not pre-loaded, mark as partial (would need API call)
            return SourceMatch(
                claim=claim,
                source_type="chart",
                source_reference=json.dumps(source_ref, ensure_ascii=False),
                status=ValidationStatus.PARTIAL,
                confidence=0.5,
                explanation=f"Chart data for {ticker} not pre-loaded. Requires market data API for full validation."
            )
    
    def _validate_event(self, claim: str, source_ref: Dict) -> SourceMatch:
        """Validate an event source reference."""
        event_id = str(source_ref.get("id", ""))
        title = source_ref.get("title", "")
        event_date = source_ref.get("date", "")
        
        if event_id in self._events:
            event = self._events[event_id]
            event_title = event.get("title", "")
            
            # Check if title matches (case-insensitive)
            if title.lower() in event_title.lower() or event_title.lower() in title.lower():
                return SourceMatch(
                    claim=claim,
                    source_type="event",
                    source_reference=json.dumps(source_ref, ensure_ascii=False),
                    source_data=event,
                    status=ValidationStatus.VALID,
                    confidence=0.95,
                    explanation=f"Event verified: {event_title} on {event_date}"
                )
            else:
                return SourceMatch(
                    claim=claim,
                    source_type="event",
                    source_reference=json.dumps(source_ref, ensure_ascii=False),
                    source_data=event,
                    status=ValidationStatus.PARTIAL,
                    confidence=0.7,
                    explanation=f"Event ID found but title differs. Expected: {title[:50]}, Got: {event_title[:50]}"
                )
        else:
            return SourceMatch(
                claim=claim,
                source_type="event",
                source_reference=json.dumps(source_ref, ensure_ascii=False),
                status=ValidationStatus.NOT_FOUND,
                explanation=f"Event not found: id={event_id}"
            )
    
    def get_tool_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "search_briefing_sources",
                "description": "Search for sources referenced in briefing scripts. Supports articles (news), charts (market data), and events (calendar).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query. Prefix with type: 'article:pk#xxx', 'article:title:...', 'chart:TICKER', 'event:id:123', 'event:title:...'"
                        },
                        "source_type": {
                            "type": "string",
                            "enum": ["article", "chart", "event", "all"],
                            "description": "Filter by source type"
                        }
                    },
                    "required": ["query"]
                }
            }
        }


# =============================================================================
# Article Source Tool (for DynamoDB/JSON news articles)
# =============================================================================

class ArticleSourceTool(SourceTool):
    """
    Source tool for news articles with pk-based identification.
    
    Handles articles from DynamoDB or JSON files with schema:
    {
        "pk": "id#xxx",
        "title": "Article Title",
        "provider": "Reuters",
        "published_date": "2025-12-22",
        "summary": "...",
        "url": "https://...",
        ...
    }
    """
    
    def __init__(self, dynamodb_table: str = None, dynamodb_profile: str = None):
        self._data: Dict[str, Dict[str, Any]] = {}  # pk -> article
        self._loaded: bool = False
        self._dynamodb_table = dynamodb_table
        self._dynamodb_profile = dynamodb_profile
    
    @property
    def source_type(self) -> str:
        return "article"
    
    def load_sources(self, path: Path) -> None:
        """Load articles from JSON files."""
        self._data = {}
        
        if path.is_file() and path.suffix == ".json":
            self._load_json(path)
        elif path.is_dir():
            for json_file in path.glob("*.json"):
                self._load_json(json_file)
        
        self._loaded = True
        logger.info(f"Loaded {len(self._data)} articles")
    
    def _load_json(self, path: Path) -> None:
        """Load articles from a JSON file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for article in data:
                        pk = article.get("pk") or article.get("id", "")
                        if pk:
                            article["_source_file"] = path.name
                            self._data[pk] = article
                elif isinstance(data, dict):
                    if "pk" in data or "id" in data:
                        pk = data.get("pk") or data.get("id", "")
                        data["_source_file"] = path.name
                        self._data[pk] = data
                    else:
                        # Assume it's a pk -> article map
                        for pk, article in data.items():
                            article["_source_file"] = path.name
                            self._data[pk] = article
        except Exception as e:
            logger.error(f"Error loading articles from {path}: {e}")
    
    def load_from_dynamodb(self, pks: List[str]) -> None:
        """Load specific articles from DynamoDB by their pks."""
        if not self._dynamodb_table:
            logger.warning("DynamoDB table not configured")
            return
        
        try:
            import boto3
            session = boto3.Session(profile_name=self._dynamodb_profile) if self._dynamodb_profile else boto3.Session()
            dynamodb = session.resource("dynamodb")
            table = dynamodb.Table(self._dynamodb_table)
            
            for pk in pks:
                if pk not in self._data:
                    try:
                        response = table.get_item(Key={"pk": pk})
                        if "Item" in response:
                            self._data[pk] = response["Item"]
                    except Exception as e:
                        logger.error(f"Error fetching article {pk}: {e}")
        except ImportError:
            logger.error("boto3 not installed, cannot load from DynamoDB")
    
    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search articles by pk or title."""
        results = []
        query_lower = query.lower()
        
        # Check if it's a pk lookup
        if query.startswith("id#") or query.startswith("pk#"):
            if query in self._data:
                return [{"pk": query, **self._data[query]}]
        
        # Title search
        for pk, article in self._data.items():
            title = article.get("title", "")
            if query_lower in title.lower():
                results.append({"pk": pk, **article})
        
        return results
    
    def search_by_pk(self, pk: str) -> Optional[Dict[str, Any]]:
        """Get a specific article by pk."""
        return self._data.get(pk)
    
    def validate_claim(self, claim: str, reference: str) -> SourceMatch:
        """
        Validate a claim against an article.
        
        Reference format: "pk:id#xxx" or just the pk string
        """
        # Parse reference
        if reference.startswith("pk:"):
            pk = reference[3:]
        else:
            pk = reference
        
        if pk in self._data:
            article = self._data[pk]
            return SourceMatch(
                claim=claim,
                source_type=self.source_type,
                source_reference=pk,
                source_data=article,
                status=ValidationStatus.VALID,
                confidence=0.95,
                explanation=f"Article found: {article.get('title', '')[:80]}"
            )
        else:
            return SourceMatch(
                claim=claim,
                source_type=self.source_type,
                source_reference=pk,
                status=ValidationStatus.NOT_FOUND,
                explanation=f"Article not found: {pk}"
            )
    
    def get_tool_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "search_article",
                "description": "Search news articles by pk (e.g., 'id#xxx') or title keywords.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Article pk (e.g., 'id#9e4894ca63cd8d66') or title keywords"
                        }
                    },
                    "required": ["query"]
                }
            }
        }


# =============================================================================
# Event Source Tool (for calendar events with numeric IDs)
# =============================================================================

class EventSourceTool(SourceTool):
    """
    Source tool for calendar events with ID-based identification.
    
    Handles events with schema:
    {
        "id": "387585",
        "title": "gdp growth rate qoq",
        "date": "2025-12-23",
        "time": "08:30 AM",
        "importance": "high",
        ...
    }
    """
    
    def __init__(self):
        self._data: Dict[str, Dict[str, Any]] = {}  # id -> event
        self._loaded: bool = False
    
    @property
    def source_type(self) -> str:
        return "event"
    
    def load_sources(self, path: Path) -> None:
        """Load events from JSON or CSV files."""
        self._data = {}
        
        if path.is_file():
            if path.suffix == ".json":
                self._load_json(path)
            elif path.suffix == ".csv":
                self._load_csv(path)
        elif path.is_dir():
            for json_file in path.glob("*.json"):
                self._load_json(json_file)
            for csv_file in path.glob("*.csv"):
                self._load_csv(csv_file)
        
        self._loaded = True
        logger.info(f"Loaded {len(self._data)} events")
    
    def _load_json(self, path: Path) -> None:
        """Load events from a JSON file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for event in data:
                        event_id = str(event.get("id", ""))
                        if event_id:
                            event["_source_file"] = path.name
                            self._data[event_id] = event
                elif isinstance(data, dict):
                    for event_id, event in data.items():
                        event["_source_file"] = path.name
                        self._data[str(event_id)] = event
        except Exception as e:
            logger.error(f"Error loading events from {path}: {e}")
    
    def _load_csv(self, path: Path) -> None:
        """Load events from a CSV file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    event_id = str(row.get("id", row.get("event_id", "")))
                    if event_id:
                        row["_source_file"] = path.name
                        self._data[event_id] = row
        except Exception as e:
            logger.error(f"Error loading events from {path}: {e}")
    
    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search events by ID or title."""
        results = []
        query_lower = query.lower()
        
        # Check if it's an ID lookup
        if query in self._data:
            return [{"id": query, **self._data[query]}]
        
        # Title search
        for event_id, event in self._data.items():
            title = event.get("title", "")
            if query_lower in title.lower():
                results.append({"id": event_id, **event})
        
        return results
    
    def search_by_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific event by ID."""
        return self._data.get(str(event_id))
    
    def validate_claim(self, claim: str, reference: str) -> SourceMatch:
        """Validate a claim against an event."""
        event_id = reference.strip()
        
        if event_id in self._data:
            event = self._data[event_id]
            return SourceMatch(
                claim=claim,
                source_type=self.source_type,
                source_reference=event_id,
                source_data=event,
                status=ValidationStatus.VALID,
                confidence=0.95,
                explanation=f"Event found: {event.get('title', '')} on {event.get('date', '')}"
            )
        else:
            return SourceMatch(
                claim=claim,
                source_type=self.source_type,
                source_reference=event_id,
                status=ValidationStatus.NOT_FOUND,
                explanation=f"Event not found: id={event_id}"
            )
    
    def get_tool_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "search_event",
                "description": "Search calendar events by ID or title keywords.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Event ID (e.g., '387585') or title keywords (e.g., 'gdp', 'fomc')"
                        },
                        "date": {
                            "type": "string",
                            "description": "Optional: Filter by date (YYYY-MM-DD)"
                        }
                    },
                    "required": ["query"]
                }
            }
        }


# =============================================================================
# Template for Custom Source Tools
# =============================================================================

class CustomSourceTool(SourceTool):
    """
    Template for creating custom source tools.
    
    Copy this class and modify for your specific data source.
    
    Steps:
    1. Copy this class with a new name
    2. Change source_type to your identifier
    3. Implement load_sources() to load your data
    4. Implement search() to search your data
    5. Implement validate_claim() to validate claims
    6. Optionally customize get_tool_definition()
    """
    
    def __init__(self):
        self._data: List[Dict[str, Any]] = []
        self._loaded: bool = False
    
    @property
    def source_type(self) -> str:
        # TODO: Change this to your source type identifier
        return "custom_source"
    
    def load_sources(self, path: Path) -> None:
        """
        Load source data from the given path.
        
        TODO: Implement your loading logic.
        
        Examples:
        - CSV: Use csv.DictReader
        - JSON: Use json.load
        - Database: Use your DB client
        - API: Use requests
        """
        self._data = []
        
        # TODO: Your loading logic here
        # Example:
        # with open(path, "r") as f:
        #     self._data = json.load(f)
        
        self._loaded = True
        logger.info(f"Loaded {len(self._data)} items for {self.source_type}")
    
    def search(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for data matching the query.
        
        TODO: Implement your search logic.
        
        Args:
            query: Search query string
            
        Returns:
            List of matching records
        """
        if not self._loaded:
            return []
        
        # TODO: Your search logic here
        results = []
        
        return results
    
    def validate_claim(self, claim: str, reference: str) -> SourceMatch:
        """
        Validate a claim against source data.
        
        TODO: Implement your validation logic.
        
        Args:
            claim: The claim text from the script
            reference: The reference string from the script
            
        Returns:
            SourceMatch with validation result
        """
        if not self._loaded:
            return SourceMatch(
                claim=claim,
                source_type=self.source_type,
                source_reference=reference,
                status=ValidationStatus.ERROR,
                explanation=f"{self.source_type} data not loaded"
            )
        
        # TODO: Your validation logic here
        
        return SourceMatch(
            claim=claim,
            source_type=self.source_type,
            source_reference=reference,
            status=ValidationStatus.NOT_FOUND,
            explanation="Validation not implemented"
        )

