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
    ArticleSourceTool,
    EventSourceTool,
    BriefingScriptSourceTool,
    YahooFinanceSourceTool,
    LiveMarketDataSourceTool,
    SECEdgarSourceTool,
)
from validation_agent.validators import (
    FactValidator,
    AudienceValidator,
    CitationValidator,
)
from validation_agent.script_validator import (
    ScriptSourceValidator,
    ScriptContentValidator,
)

logger = logging.getLogger(__name__)


class ClosingBriefingValidator:
    """
    Pre-configured validator for closing_briefing AI agent outputs.
    
    Runs ALL validators automatically:
    - FactValidator: Validates facts against source data
    - AudienceValidator: Checks content fitness for target audience
    - CitationValidator: Ensures all claims have proper citations
    - ScriptSourceValidator: Validates embedded source references
    - ScriptContentValidator: Uses LLM to verify content matches sources
    
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
        articles_path: Optional[Path] = None,
        events_path: Optional[Path] = None,
        yahoo_finance_path: Optional[Path] = None,
        market_data_path: Optional[Path] = None,
        sec_edgar_path: Optional[Path] = None,
        yahoo_dynamodb_table: str = "kubig-YahoofinanceNews",
        yahoo_dynamodb_region: str = "ap-northeast-2",
        yahoo_dynamodb_profile: str = "jonghyun",
    ):
        """
        Initialize the validator.
        
        Args:
            te_output_path: Path to te_calendar_scraper output directory
            news_path: Optional path to news data (JSON files)
            articles_path: Optional path to articles data (for structured scripts)
            events_path: Optional path to events data (for structured scripts)
            yahoo_finance_path: Fallback path for Yahoo Finance news (if DynamoDB unavailable)
            market_data_path: Path to live/cached market data (JSON/CSV)
            sec_edgar_path: Path to SEC Edgar filings (JSON)
            yahoo_dynamodb_table: DynamoDB table for Yahoo Finance news
            yahoo_dynamodb_region: AWS region for DynamoDB
            yahoo_dynamodb_profile: AWS SSO profile for DynamoDB authentication
        """
        self.te_output_path = Path(te_output_path) if te_output_path else Path("/home/jhkim/te_calendar_scraper/output")
        self.news_path = Path(news_path) if news_path else None
        self.articles_path = Path(articles_path) if articles_path else None
        self.events_path = Path(events_path) if events_path else None
        self.yahoo_finance_path = Path(yahoo_finance_path) if yahoo_finance_path else None
        self.market_data_path = Path(market_data_path) if market_data_path else None
        self.sec_edgar_path = Path(sec_edgar_path) if sec_edgar_path else None
        
        # DynamoDB config
        self._yahoo_dynamodb_table = yahoo_dynamodb_table
        self._yahoo_dynamodb_region = yahoo_dynamodb_region
        self._yahoo_dynamodb_profile = yahoo_dynamodb_profile
        
        # Initialize validation agent
        self._agent = ValidationAgent()
        
        # Register ALL source tools
        self._agent.register_source_tool(TECalendarSourceTool())
        self._agent.register_source_tool(TEIndicatorsSourceTool())
        self._agent.register_source_tool(FOMCSourceTool())
        self._agent.register_source_tool(NewsSourceTool())
        self._agent.register_source_tool(ArticleSourceTool())
        self._agent.register_source_tool(EventSourceTool())
        self._agent.register_source_tool(BriefingScriptSourceTool())
        
        # Yahoo Finance News (DynamoDB or local fallback)
        self._agent.register_source_tool(YahooFinanceSourceTool(
            table_name=yahoo_dynamodb_table,
            region=yahoo_dynamodb_region,
            profile=yahoo_dynamodb_profile,
        ))
        
        # Live Market Data (local path)
        self._agent.register_source_tool(LiveMarketDataSourceTool(
            data_path=market_data_path,
        ))
        
        # SEC Edgar (local path)
        self._agent.register_source_tool(SECEdgarSourceTool(
            data_path=sec_edgar_path,
        ))
        
        # Register ALL validators
        self._agent.register_validator(FactValidator())
        self._agent.register_validator(AudienceValidator())
        self._agent.register_validator(CitationValidator())
        self._agent.register_validator(ScriptSourceValidator())
        self._agent.register_validator(ScriptContentValidator())
        
        self._sources_loaded = False
    
    def load_sources(self) -> None:
        """Load source data from configured paths."""
        source_paths = {}
        
        # te_calendar_scraper paths
        if self.te_output_path.exists():
            calendar_path = self.te_output_path / "calendar"
            if calendar_path.exists():
                source_paths["calendar_events"] = calendar_path
            
            indicators_path = self.te_output_path / "indicators"
            if indicators_path.exists():
                source_paths["macro_data"] = indicators_path
            
            fomc_path = self.te_output_path / "fomc_press_conferences"
            if fomc_path.exists():
                source_paths["fomc_events"] = fomc_path
        
        # Additional paths
        if self.news_path and self.news_path.exists():
            source_paths["news_data"] = self.news_path
        
        if self.articles_path and self.articles_path.exists():
            source_paths["article"] = self.articles_path
        
        if self.events_path and self.events_path.exists():
            source_paths["event"] = self.events_path
        
        # Yahoo Finance fallback path (uses DynamoDB by default)
        if self.yahoo_finance_path and self.yahoo_finance_path.exists():
            source_paths["yahoo_finance_news"] = self.yahoo_finance_path
        
        # Market data path
        if self.market_data_path and self.market_data_path.exists():
            source_paths["live_market_data"] = self.market_data_path
        
        # SEC Edgar path
        if self.sec_edgar_path and self.sec_edgar_path.exists():
            source_paths["sec_edgar"] = self.sec_edgar_path
        
        self._agent.load_sources(source_paths)
        self._sources_loaded = True
        
        logger.info(f"Loaded sources: {list(source_paths.keys())}")
    
    def validate(self, script: str, script_id: str = None) -> ValidationResult:
        """
        Validate a script using ALL validators.
        
        Args:
            script: The script text or JSON to validate
            script_id: Optional identifier for tracking
                       
        Returns:
            ValidationResult with detailed validation outcomes
        """
        if not self._sources_loaded:
            logger.warning("Sources not loaded, attempting to load now")
            self.load_sources()
        
        return self._agent.validate(script=script, script_id=script_id)
    
    def get_tool_definitions(self):
        """Get all tool definitions for external use."""
        return self._agent.get_tool_definitions()


def create_closing_briefing_validator(
    te_calendar_output_path: str = None,
    news_path: str = None,
    articles_path: str = None,
    events_path: str = None,
    yahoo_finance_path: str = None,
    market_data_path: str = None,
    sec_edgar_path: str = None,
    yahoo_dynamodb_table: str = "kubig-YahoofinanceNews",
    yahoo_dynamodb_region: str = "ap-northeast-2",
    yahoo_dynamodb_profile: str = "jonghyun",
    auto_load_sources: bool = True,
) -> ClosingBriefingValidator:
    """
    Factory function to create a pre-configured closing briefing validator.
    
    Runs ALL validators automatically - no mode selection needed.
    
    Args:
        te_calendar_output_path: Path to te_calendar_scraper output
        news_path: Optional path to news data
        articles_path: Optional path to articles data
        events_path: Optional path to events data
        yahoo_finance_path: Fallback path for Yahoo Finance news (if DynamoDB unavailable)
        market_data_path: Path to live/cached market data (JSON/CSV)
        sec_edgar_path: Path to SEC Edgar filings (JSON)
        yahoo_dynamodb_table: DynamoDB table for Yahoo Finance news
        yahoo_dynamodb_region: AWS region for DynamoDB
        yahoo_dynamodb_profile: AWS SSO profile for DynamoDB authentication
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
        articles_path=Path(articles_path) if articles_path else None,
        events_path=Path(events_path) if events_path else None,
        yahoo_finance_path=Path(yahoo_finance_path) if yahoo_finance_path else None,
        market_data_path=Path(market_data_path) if market_data_path else None,
        sec_edgar_path=Path(sec_edgar_path) if sec_edgar_path else None,
        yahoo_dynamodb_table=yahoo_dynamodb_table,
        yahoo_dynamodb_region=yahoo_dynamodb_region,
        yahoo_dynamodb_profile=yahoo_dynamodb_profile,
    )
    
    if auto_load_sources:
        try:
            validator.load_sources()
        except Exception as e:
            logger.warning(f"Failed to auto-load sources: {e}")
    
    return validator
