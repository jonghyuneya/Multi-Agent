"""
Configuration for the Validation Agent.

This module provides configuration settings that can be customized
for different validation scenarios.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

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
# Validation Configuration
# =============================================================================

@dataclass
class ValidationConfig:
    """Configuration for validation runs."""
    
    # Source paths
    calendar_path: Path = field(default_factory=lambda: DEFAULT_CALENDAR_PATH)
    indicators_path: Path = field(default_factory=lambda: DEFAULT_INDICATORS_PATH)
    fomc_path: Path = field(default_factory=lambda: DEFAULT_FOMC_PATH)
    news_path: Optional[Path] = None
    
    # LLM settings
    model: str = "gpt-4o"
    temperature: float = 0.1
    max_tool_iterations: int = 10
    
    # Validation settings
    validators: List[str] = field(default_factory=lambda: ["fact", "audience", "citation"])
    
    # Output settings
    output_dir: Optional[Path] = None
    save_results: bool = True
    
    def get_source_paths(self) -> Dict[str, Path]:
        """Get all configured source paths."""
        paths = {
            "calendar_events": self.calendar_path,
            "macro_data": self.indicators_path,
            "fomc_events": self.fomc_path,
        }
        
        if self.news_path:
            paths["news_data"] = self.news_path
        
        return paths
    
    @classmethod
    def from_env(cls) -> "ValidationConfig":
        """Create configuration from environment variables."""
        return cls(
            calendar_path=Path(os.getenv("VALIDATION_CALENDAR_PATH", str(DEFAULT_CALENDAR_PATH))),
            indicators_path=Path(os.getenv("VALIDATION_INDICATORS_PATH", str(DEFAULT_INDICATORS_PATH))),
            fomc_path=Path(os.getenv("VALIDATION_FOMC_PATH", str(DEFAULT_FOMC_PATH))),
            news_path=Path(os.getenv("VALIDATION_NEWS_PATH")) if os.getenv("VALIDATION_NEWS_PATH") else None,
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            output_dir=Path(os.getenv("VALIDATION_OUTPUT_DIR")) if os.getenv("VALIDATION_OUTPUT_DIR") else None,
        )


# =============================================================================
# Source Tool Registry
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
}


# =============================================================================
# Target Audience Configuration
# =============================================================================

@dataclass
class AudienceConfig:
    """Configuration for target audience validation."""
    
    # Primary audience
    primary: str = "경제 뉴스와 주식 시장에 관심 있는 투자자"
    
    # Audience characteristics
    characteristics: List[str] = field(default_factory=lambda: [
        "금융 기초 지식 보유",
        "주식/채권 투자 경험",
        "경제 지표에 대한 관심",
        "시장 동향 파악 욕구",
    ])
    
    # Content requirements
    requirements: List[str] = field(default_factory=lambda: [
        "전문적이면서 이해하기 쉬운 설명",
        "투자 판단에 도움이 되는 분석",
        "신뢰할 수 있는 출처 기반",
        "균형 잡힌 시각",
    ])


# =============================================================================
# Validator Thresholds
# =============================================================================

@dataclass
class ValidationThresholds:
    """Thresholds for validation pass/fail decisions."""
    
    # Minimum percentage of valid claims to pass
    min_valid_claim_ratio: float = 0.9  # 90%
    
    # Maximum allowed invalid claims
    max_invalid_claims: int = 0
    
    # Maximum allowed missing citations
    max_missing_citations: int = 2
    
    # Minimum audience fitness
    min_audience_fitness: str = "good"  # excellent, good, fair, poor
    
    def check_passed(self, result) -> bool:
        """Check if validation result passes thresholds."""
        if result.total_claims > 0:
            valid_ratio = result.valid_claims / result.total_claims
            if valid_ratio < self.min_valid_claim_ratio:
                return False
        
        if result.invalid_claims > self.max_invalid_claims:
            return False
        
        if len(result.missing_citations) > self.max_missing_citations:
            return False
        
        fitness_order = ["excellent", "good", "fair", "poor"]
        if fitness_order.index(result.audience_fitness.value) > fitness_order.index(self.min_audience_fitness):
            return False
        
        return True

