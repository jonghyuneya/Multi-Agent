"""
Configuration for the Validation Agent.

This module provides configuration settings for validation.
"""

from __future__ import annotations

import os
from pathlib import Path

# =============================================================================
# Default Paths
# =============================================================================

# TradingEconomics calendar scraper output
DEFAULT_TE_OUTPUT_PATH = Path("/home/jhkim/te_calendar_scraper/output")

# Subdirectories
DEFAULT_CALENDAR_PATH = DEFAULT_TE_OUTPUT_PATH / "calendar"
DEFAULT_INDICATORS_PATH = DEFAULT_TE_OUTPUT_PATH / "indicators"
DEFAULT_FOMC_PATH = DEFAULT_TE_OUTPUT_PATH / "fomc_press_conferences"

# =============================================================================
# LLM Configuration
# =============================================================================

# OpenAI settings
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_TEMPERATURE = 0.1  # Low for factual validation

# Max iterations for tool calling
MAX_TOOL_ITERATIONS = 10

# =============================================================================
# Source Tool Configuration
# =============================================================================

# Map source types to their configuration
SOURCE_TOOL_CONFIG = {
    "calendar_events": {
        "description": "TradingEconomics economic calendar events",
        "default_path": DEFAULT_CALENDAR_PATH,
        "file_pattern": "calendar_*.csv",
    },
    "macro_data": {
        "description": "TradingEconomics macroeconomic indicators",
        "default_path": DEFAULT_INDICATORS_PATH,
        "file_pattern": "indicators_*.csv",
    },
    "fomc_events": {
        "description": "Federal Reserve FOMC press conferences",
        "default_path": DEFAULT_FOMC_PATH,
        "file_pattern": "*.pdf",
    },
    "news_data": {
        "description": "News articles (JSON format)",
        "default_path": None,
        "file_pattern": "*.json",
    },
    "article": {
        "description": "News articles with pk identifiers",
        "default_path": None,
        "file_pattern": "*.json",
    },
    "event": {
        "description": "Calendar events with id identifiers",
        "default_path": None,
        "file_pattern": "*.json",
    },
}

# =============================================================================
# Target Audience
# =============================================================================

TARGET_AUDIENCE = "경제 뉴스와 주식 시장에 관심 있는 투자자"

AUDIENCE_CHARACTERISTICS = [
    "금융 기초 지식 보유",
    "주식/채권 투자 경험",
    "경제 지표에 대한 관심",
    "시장 동향 파악 욕구",
]

# =============================================================================
# Validation Thresholds
# =============================================================================

# Minimum percentage of valid claims to pass
MIN_VALID_CLAIM_RATIO = 0.9  # 90%

# Maximum allowed invalid claims
MAX_INVALID_CLAIMS = 0

# Maximum allowed missing citations
MAX_MISSING_CITATIONS = 2

# Minimum audience fitness to pass
MIN_AUDIENCE_FITNESS = "good"  # excellent, good, fair, poor
