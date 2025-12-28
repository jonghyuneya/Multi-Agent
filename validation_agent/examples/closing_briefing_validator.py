"""
Closing Briefing Validator - Example implementation.

This module shows how to configure the Validation Agent for
validating closing_briefing AI agent outputs.

Usage:
    from validation_agent.examples import create_closing_briefing_validator
    
    validator = create_closing_briefing_validator(
        te_calendar_output_path="/home/jhkim/te_calendar_scraper/output"
    )
    
    result = validator.validate(script_text)
    print(result.summary)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from validation_agent.base import ValidationAgent, ValidationResult
from validation_agent.source_tools import (
    TECalendarSourceTool,
    TEIndicatorsSourceTool,
    FOMCSourceTool,
    NewsSourceTool,
)
from validation_agent.validators import (
    FactValidator,
    AudienceValidator,
    CitationValidator,
)

logger = logging.getLogger(__name__)


class ClosingBriefingValidator:
    """
    Pre-configured validator for closing_briefing AI agent outputs.
    
    This validator is configured to validate scripts against:
    - TradingEconomics calendar data
    - TradingEconomics indicator data
    - FOMC press conference documents
    - News articles (if available)
    
    Example:
        validator = ClosingBriefingValidator(
            te_output_path=Path("/home/jhkim/te_calendar_scraper/output")
        )
        
        # Load sources
        validator.load_sources()
        
        # Validate a script
        result = validator.validate(script_text)
        
        # Check results
        if not result.overall_valid:
            print("Issues found:")
            for match in result.source_matches:
                if match.status.value != "valid":
                    print(f"  - {match.claim}: {match.explanation}")
    """
    
    def __init__(
        self,
        te_output_path: Path = None,
        news_path: Optional[Path] = None,
    ):
        """
        Initialize the validator.
        
        Args:
            te_output_path: Path to te_calendar_scraper output directory
            news_path: Optional path to news data (JSON files)
        """
        self.te_output_path = Path(te_output_path) if te_output_path else Path("/home/jhkim/te_calendar_scraper/output")
        self.news_path = Path(news_path) if news_path else None
        
        # Initialize validation agent
        self._agent = ValidationAgent()
        
        # Register source tools
        self._agent.register_source_tool(TECalendarSourceTool())
        self._agent.register_source_tool(TEIndicatorsSourceTool())
        self._agent.register_source_tool(FOMCSourceTool())
        
        if self.news_path:
            self._agent.register_source_tool(NewsSourceTool())
        
        # Register validators
        self._agent.register_validator(FactValidator())
        self._agent.register_validator(AudienceValidator())
        self._agent.register_validator(CitationValidator())
        
        self._sources_loaded = False
    
    def load_sources(self) -> None:
        """Load source data from configured paths."""
        source_paths = {
            "calendar_events": self.te_output_path / "calendar",
            "macro_data": self.te_output_path / "indicators",
            "fomc_events": self.te_output_path / "fomc_press_conferences",
        }
        
        if self.news_path:
            source_paths["news_data"] = self.news_path
        
        self._agent.load_sources(source_paths)
        self._sources_loaded = True
        
        logger.info("Loaded all sources for closing_briefing validation")
    
    def validate(
        self,
        script: str,
        script_id: str = None,
        validators: list = None,
    ) -> ValidationResult:
        """
        Validate a closing briefing script.
        
        Args:
            script: The script text to validate
            script_id: Optional identifier for tracking
            validators: Optional list of validators to run
                       ("fact", "audience", "citation")
                       Default: all validators
                       
        Returns:
            ValidationResult with detailed validation outcomes
        """
        if not self._sources_loaded:
            logger.warning("Sources not loaded, attempting to load now")
            self.load_sources()
        
        return self._agent.validate(
            script=script,
            script_id=script_id,
            validators=validators,
        )
    
    def validate_fact_only(self, script: str) -> ValidationResult:
        """Run only fact validation."""
        return self.validate(script, validators=["fact"])
    
    def validate_audience_only(self, script: str) -> ValidationResult:
        """Run only audience fitness validation."""
        return self.validate(script, validators=["audience"])
    
    def validate_citations_only(self, script: str) -> ValidationResult:
        """Run only citation validation."""
        return self.validate(script, validators=["citation"])
    
    def get_tool_definitions(self):
        """Get all tool definitions for external use."""
        return self._agent.get_tool_definitions()


def create_closing_briefing_validator(
    te_calendar_output_path: str = None,
    news_path: str = None,
    auto_load_sources: bool = True,
) -> ClosingBriefingValidator:
    """
    Factory function to create a pre-configured closing briefing validator.
    
    Args:
        te_calendar_output_path: Path to te_calendar_scraper output
        news_path: Optional path to news data
        auto_load_sources: Whether to auto-load sources on creation
        
    Returns:
        Configured ClosingBriefingValidator instance
        
    Example:
        validator = create_closing_briefing_validator()
        result = validator.validate(my_script)
    """
    validator = ClosingBriefingValidator(
        te_output_path=Path(te_calendar_output_path) if te_calendar_output_path else None,
        news_path=Path(news_path) if news_path else None,
    )
    
    if auto_load_sources:
        try:
            validator.load_sources()
        except Exception as e:
            logger.warning(f"Failed to auto-load sources: {e}")
    
    return validator

