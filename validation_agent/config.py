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
    "yahoo_finance_news": {
        "description": "Yahoo Finance news from AWS DynamoDB (kubig-YahoofinanceNews)",
        "default_path": None,  # Uses DynamoDB by default
        "file_pattern": "*.json",  # Fallback to local JSON
        "dynamodb_table": "kubig-YahoofinanceNews",
        "dynamodb_region": "ap-northeast-2",
        "dynamodb_profile": "jonghyun",
    },
    "live_market_data": {
        "description": "Live/recent market data (prices, indices, sectors)",
        "default_path": None,  # Must be provided by user
        "file_pattern": "*.json",
        "note": "Load from local JSON/CSV or integrate with market data API",
    },
    "sec_edgar": {
        "description": "SEC Edgar filings (10-K, 10-Q, 8-K, etc.)",
        "default_path": None,  # Must be provided by user
        "file_pattern": "*.json",
        "note": "Load from local files or integrate with SEC Edgar API",
    },
}

# =============================================================================
# DynamoDB Configuration (Yahoo Finance News)
# =============================================================================

YAHOO_FINANCE_DYNAMODB_TABLE = os.getenv("YAHOO_FINANCE_TABLE", "kubig-YahoofinanceNews")
YAHOO_FINANCE_DYNAMODB_REGION = os.getenv("YAHOO_FINANCE_REGION", "ap-northeast-2")
YAHOO_FINANCE_DYNAMODB_PROFILE = os.getenv("YAHOO_FINANCE_PROFILE", "jonghyun")

# =============================================================================
# Market Data Configuration
# =============================================================================

# Default path for cached market data (if available)
DEFAULT_MARKET_DATA_PATH = os.getenv("MARKET_DATA_PATH", None)

# =============================================================================
# SEC Edgar Configuration
# =============================================================================

# Default path for cached SEC filings (if available)
DEFAULT_SEC_EDGAR_PATH = os.getenv("SEC_EDGAR_PATH", None)

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
