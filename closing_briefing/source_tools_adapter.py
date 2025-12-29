"""
Source Tools Adapter for Closing Briefing.

This module integrates the validation_agent's SourceTool classes into the
closing_briefing's LLM tool-calling system.

Instead of using custom data loading logic, the agent now uses the same source tools
as the validation_agent:
- TECalendarSourceTool -> calendar events
- TEIndicatorsSourceTool -> macro indicators
- NewsSourceTool -> news articles
- FOMCSourceTool -> FOMC events
- YahooFinanceSourceTool -> Yahoo Finance news
- LiveMarketDataSourceTool -> market data
- SECEdgarSourceTool -> SEC filings

Usage:
    from closing_briefing.source_tools_adapter import (
        BriefingSourceToolAdapter,
        create_briefing_tools,
        create_tool_executor,
    )
    
    # Create tools and executor
    tools = create_briefing_tools()
    executor = create_tool_executor(sources_config)
    
    # Use in LLM call
    response = call_llm_with_tools(prompt, message, tools, executor)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import validation_agent source tools
try:
    from validation_agent.source_tools import (
        TECalendarSourceTool,
        TEIndicatorsSourceTool,
        FOMCSourceTool,
        NewsSourceTool,
        YahooFinanceSourceTool,
        LiveMarketDataSourceTool,
        SECEdgarSourceTool,
        ArticleSourceTool,
        EventSourceTool,
    )
    VALIDATION_AGENT_AVAILABLE = True
except ImportError:
    VALIDATION_AGENT_AVAILABLE = False

logger = logging.getLogger(__name__)


# =============================================================================
# Source Configuration
# =============================================================================

@dataclass
class SourceConfig:
    """Configuration for source data paths and settings."""
    
    # TradingEconomics data paths (can be str or Path)
    te_calendar_path: Optional[Path] = None
    te_indicators_path: Optional[Path] = None
    te_fomc_path: Optional[Path] = None
    
    # News data paths
    news_path: Optional[Path] = None
    
    # Yahoo Finance DynamoDB
    yahoo_finance_table: str = "kubig-YahoofinanceNews"
    yahoo_finance_region: str = "ap-northeast-2"
    yahoo_finance_profile: str = "jonghyun"
    yahoo_finance_local_path: Optional[Path] = None
    
    # Market data
    market_data_path: Optional[Path] = None
    
    # SEC Edgar
    sec_edgar_path: Optional[Path] = None
    
    # Briefing date
    briefing_date: Optional[str] = None
    
    def __post_init__(self):
        """Convert string paths to Path objects."""
        if self.te_calendar_path and isinstance(self.te_calendar_path, str):
            self.te_calendar_path = Path(self.te_calendar_path)
        if self.te_indicators_path and isinstance(self.te_indicators_path, str):
            self.te_indicators_path = Path(self.te_indicators_path)
        if self.te_fomc_path and isinstance(self.te_fomc_path, str):
            self.te_fomc_path = Path(self.te_fomc_path)
        if self.news_path and isinstance(self.news_path, str):
            self.news_path = Path(self.news_path)
        if self.yahoo_finance_local_path and isinstance(self.yahoo_finance_local_path, str):
            self.yahoo_finance_local_path = Path(self.yahoo_finance_local_path)
        if self.market_data_path and isinstance(self.market_data_path, str):
            self.market_data_path = Path(self.market_data_path)
        if self.sec_edgar_path and isinstance(self.sec_edgar_path, str):
            self.sec_edgar_path = Path(self.sec_edgar_path)
    
    @classmethod
    def from_te_scraper_output(cls, te_output_path: str, **kwargs) -> "SourceConfig":
        """Create config from te_calendar_scraper output directory."""
        te_path = Path(te_output_path)
        return cls(
            te_calendar_path=te_path / "calendar",
            te_indicators_path=te_path / "indicators",
            te_fomc_path=te_path / "fomc_press_conferences",
            **kwargs
        )


# =============================================================================
# Tool Definitions for OpenAI Function Calling
# =============================================================================

def create_briefing_tools() -> List[Dict[str, Any]]:
    """
    Create OpenAI function calling tool definitions.
    
    These tools wrap the validation_agent's SourceTool classes.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "search_calendar_events",
                "description": "Search economic calendar events by title, category, or date. Returns events from TradingEconomics calendar.",
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
                        },
                        "importance": {
                            "type": "string",
                            "enum": ["high", "medium", "low", "all"],
                            "description": "Filter by importance level (default: all)"
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_macro_indicators",
                "description": "Search macroeconomic indicators (CPI, PMI, yields, etc.) from TradingEconomics.",
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
        },
        {
            "type": "function",
            "function": {
                "name": "search_news_articles",
                "description": "Search news articles by headline, provider, or content.",
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
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results (default: 10)"
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_fomc_events",
                "description": "Search FOMC press conference documents and Fed meeting information.",
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
        },
        {
            "type": "function",
            "function": {
                "name": "search_yahoo_finance_news",
                "description": "Search Yahoo Finance news articles. Use 'ticker:' prefix for ticker search, 'provider:' for provider search.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query. Use 'ticker:AAPL' for ticker, 'provider:Reuters' for provider, or keywords for title search."
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_market_data",
                "description": "Search live/recent market data by ticker symbol or index name. Returns price, change, volume data.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "Ticker symbol (e.g., '^GSPC', 'AAPL', '^DJI') or index name (e.g., 'S&P 500')"
                        },
                        "date": {
                            "type": "string",
                            "description": "Optional: Specific date for historical data (YYYY-MM-DD)"
                        }
                    },
                    "required": ["ticker"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_sec_filings",
                "description": "Search SEC Edgar filings. Use 'cik:', 'company:', 'form:', or 'accession:' prefixes.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query. Use 'cik:0000320193', 'company:Apple', 'form:10-K', or keywords."
                        },
                        "form_type": {
                            "type": "string",
                            "description": "Optional: Filter by form type (10-K, 10-Q, 8-K, etc.)"
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_all_sources_summary",
                "description": "Get a summary of all available source data. Use this to understand what data is available.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        },
    ]


# =============================================================================
# Unified Tool Executor
# =============================================================================

class BriefingSourceToolAdapter:
    """
    Adapter that uses validation_agent's SourceTool classes for the briefing agent.
    
    This provides a unified interface for the LLM to access all source data
    through tool calls, using the same tools as the validation agent.
    """
    
    def __init__(self, config: SourceConfig):
        """
        Initialize the adapter with source configuration.
        
        Args:
            config: SourceConfig with paths and settings
        """
        self.config = config
        self.briefing_date = config.briefing_date or datetime.now().strftime('%Y-%m-%d')
        
        # Initialize source tools
        self._tools: Dict[str, Any] = {}
        self._references: List[Dict[str, Any]] = []
        
        self._init_source_tools()
    
    def _init_source_tools(self) -> None:
        """Initialize all source tools based on configuration."""
        if not VALIDATION_AGENT_AVAILABLE:
            logger.warning("validation_agent not available, using fallback mode")
            return
        
        # TradingEconomics Calendar
        if self.config.te_calendar_path:
            try:
                tool = TECalendarSourceTool()
                tool.load_sources(self.config.te_calendar_path)
                self._tools["calendar"] = tool
                logger.info(f"Loaded calendar tool from {self.config.te_calendar_path}")
            except Exception as e:
                logger.error(f"Failed to load calendar tool: {e}")
        
        # TradingEconomics Indicators
        if self.config.te_indicators_path:
            try:
                tool = TEIndicatorsSourceTool()
                tool.load_sources(self.config.te_indicators_path)
                self._tools["indicators"] = tool
                logger.info(f"Loaded indicators tool from {self.config.te_indicators_path}")
            except Exception as e:
                logger.error(f"Failed to load indicators tool: {e}")
        
        # FOMC
        if self.config.te_fomc_path:
            try:
                tool = FOMCSourceTool()
                tool.load_sources(self.config.te_fomc_path)
                self._tools["fomc"] = tool
                logger.info(f"Loaded FOMC tool from {self.config.te_fomc_path}")
            except Exception as e:
                logger.error(f"Failed to load FOMC tool: {e}")
        
        # News
        if self.config.news_path:
            try:
                tool = NewsSourceTool()
                tool.load_sources(self.config.news_path)
                self._tools["news"] = tool
                logger.info(f"Loaded news tool from {self.config.news_path}")
            except Exception as e:
                logger.error(f"Failed to load news tool: {e}")
        
        # Yahoo Finance News
        if self.config.yahoo_finance_local_path or self.config.yahoo_finance_table:
            try:
                tool = YahooFinanceSourceTool(
                    table_name=self.config.yahoo_finance_table,
                    region=self.config.yahoo_finance_region,
                    profile=self.config.yahoo_finance_profile,
                )
                local_path = self.config.yahoo_finance_local_path or Path(".")
                tool.load_sources(local_path)
                self._tools["yahoo_finance"] = tool
                logger.info("Loaded Yahoo Finance news tool")
            except Exception as e:
                logger.warning(f"Failed to load Yahoo Finance tool: {e}")
        
        # Market Data
        if self.config.market_data_path:
            try:
                tool = LiveMarketDataSourceTool()
                tool.load_sources(self.config.market_data_path)
                self._tools["market_data"] = tool
                logger.info(f"Loaded market data tool from {self.config.market_data_path}")
            except Exception as e:
                logger.error(f"Failed to load market data tool: {e}")
        
        # SEC Edgar
        if self.config.sec_edgar_path:
            try:
                tool = SECEdgarSourceTool()
                tool.load_sources(self.config.sec_edgar_path)
                self._tools["sec_edgar"] = tool
                logger.info(f"Loaded SEC Edgar tool from {self.config.sec_edgar_path}")
            except Exception as e:
                logger.error(f"Failed to load SEC Edgar tool: {e}")
    
    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool call and return results with source references.
        
        Args:
            tool_name: Name of the tool (from LLM function call)
            arguments: Tool arguments
            
        Returns:
            Dictionary with 'data' and 'references' keys
        """
        logger.info(f"Executing tool: {tool_name} with args: {arguments}")
        
        tool_handlers = {
            "search_calendar_events": self._search_calendar,
            "search_macro_indicators": self._search_indicators,
            "search_news_articles": self._search_news,
            "search_fomc_events": self._search_fomc,
            "search_yahoo_finance_news": self._search_yahoo_finance,
            "search_market_data": self._search_market_data,
            "search_sec_filings": self._search_sec_edgar,
            "get_all_sources_summary": self._get_sources_summary,
        }
        
        handler = tool_handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}", "references": []}
        
        try:
            return handler(arguments)
        except Exception as e:
            logger.error(f"Error executing {tool_name}: {e}")
            return {"error": str(e), "references": []}
    
    def _create_reference(
        self,
        source_type: str,
        quote: str,
        source_file: str = "",
        provider: str = None,
        date: str = None,
        pk: str = None,
        id_: str = None,
        ticker: str = None,
        meta: Dict = None,
    ) -> Dict[str, Any]:
        """Create a standardized reference object."""
        ref = {
            "source_type": source_type,
            "source_file": source_file,
            "quote": quote,
            "date": date or self.briefing_date,
        }
        
        # Add type-specific identifiers
        if provider:
            ref["provider"] = provider
        if pk:
            ref["pk"] = pk
            ref["type"] = "article"
        if id_:
            ref["id"] = id_
            ref["type"] = "event"
        if ticker:
            ref["ticker"] = ticker
            ref["type"] = "chart"
        if meta:
            ref["meta"] = meta
        
        self._references.append(ref)
        return ref
    
    def _search_calendar(self, args: Dict) -> Dict[str, Any]:
        """Search calendar events."""
        query = args.get("query", "")
        date_filter = args.get("date")
        importance = args.get("importance", "all")
        
        if "calendar" not in self._tools:
            return {"data": [], "references": [], "message": "Calendar data not loaded"}
        
        results = self._tools["calendar"].search(query)
        
        # Filter by date if provided
        if date_filter:
            results = [r for r in results if date_filter in r.get("datetime_utc", "") or date_filter in r.get("datetime_kst", "")]
        
        # Filter by importance
        if importance != "all":
            results = [r for r in results if r.get("impact", "").lower() == importance]
        
        # Create references
        references = []
        for event in results:
            ref = self._create_reference(
                source_type="calendar_events",
                quote=f"{event.get('title', '')}, {event.get('datetime_kst', '')}",
                source_file=event.get("_source_file", "calendar.csv"),
                date=event.get("datetime_kst", "")[:10] if event.get("datetime_kst") else None,
                id_=str(event.get("id", "")),
            )
            references.append(ref)
        
        return {"data": results, "references": references}
    
    def _search_indicators(self, args: Dict) -> Dict[str, Any]:
        """Search macro indicators."""
        query = args.get("query", "")
        bucket = args.get("bucket")
        
        if "indicators" not in self._tools:
            return {"data": [], "references": [], "message": "Indicator data not loaded"}
        
        results = self._tools["indicators"].search(query)
        
        # Filter by bucket if provided
        if bucket:
            results = [r for r in results if bucket.lower() in r.get("indicator_bucket", "").lower()]
        
        # Create references
        references = []
        for indicator in results:
            value = indicator.get("latest_value", "")
            unit = indicator.get("unit", "")
            name = indicator.get("indicator_name", "")
            
            ref = self._create_reference(
                source_type="macro_data",
                quote=f"{name}: {value}{unit}",
                source_file=indicator.get("_source_file", "indicators.csv"),
                date=indicator.get("obs_date"),
                meta={"bucket": indicator.get("indicator_bucket")}
            )
            references.append(ref)
        
        return {"data": results, "references": references}
    
    def _search_news(self, args: Dict) -> Dict[str, Any]:
        """Search news articles."""
        query = args.get("query", "")
        provider_filter = args.get("provider")
        limit = args.get("limit", 10)
        
        if "news" not in self._tools:
            return {"data": [], "references": [], "message": "News data not loaded"}
        
        results = self._tools["news"].search(query)
        
        # Filter by provider if provided
        if provider_filter:
            results = [
                r for r in results
                if provider_filter.lower() in (r.get("provider", "") or r.get("source", "")).lower()
            ]
        
        results = results[:limit]
        
        # Create references
        references = []
        for article in results:
            headline = article.get("headline", "") or article.get("title", "")
            provider = article.get("provider", "") or article.get("source", "")
            pk = article.get("pk") or article.get("id")
            
            ref = self._create_reference(
                source_type="news_data",
                quote=f'"{headline}"',
                source_file=article.get("_source_file", "news.json"),
                provider=provider,
                date=article.get("published_date"),
                pk=pk,
            )
            references.append(ref)
        
        return {"data": results, "references": references}
    
    def _search_fomc(self, args: Dict) -> Dict[str, Any]:
        """Search FOMC events."""
        query = args.get("query", "")
        
        if "fomc" not in self._tools:
            return {"data": [], "references": [], "message": "FOMC data not loaded"}
        
        results = self._tools["fomc"].search(query)
        
        # Create references
        references = []
        for event in results:
            ref = self._create_reference(
                source_type="fomc_events",
                quote=f"{event.get('title', '')}, {event.get('year', '')}-{event.get('month', '')}",
                source_file=event.get("filename", ""),
                date=f"{event.get('year', '')}-{event.get('month', '')}",
            )
            references.append(ref)
        
        return {"data": results, "references": references}
    
    def _search_yahoo_finance(self, args: Dict) -> Dict[str, Any]:
        """Search Yahoo Finance news."""
        query = args.get("query", "")
        
        if "yahoo_finance" not in self._tools:
            return {"data": [], "references": [], "message": "Yahoo Finance data not loaded"}
        
        results = self._tools["yahoo_finance"].search(query)
        
        # Create references
        references = []
        for article in results:
            ref = self._create_reference(
                source_type="yahoo_finance_news",
                quote=f'"{article.get("title", "")}"',
                source_file="DynamoDB:kubig-YahoofinanceNews",
                provider=article.get("provider", "Yahoo Finance"),
                date=article.get("publish_et_iso", "")[:10] if article.get("publish_et_iso") else None,
                pk=article.get("pk"),
                meta={"tickers": article.get("tickers", [])}
            )
            references.append(ref)
        
        return {"data": results, "references": references}
    
    def _search_market_data(self, args: Dict) -> Dict[str, Any]:
        """Search market data."""
        ticker = args.get("ticker", "")
        date = args.get("date")
        
        if "market_data" not in self._tools:
            return {"data": [], "references": [], "message": "Market data not loaded"}
        
        results = self._tools["market_data"].search(ticker)
        
        # Create references
        references = []
        for data_point in results:
            close = data_point.get("close", "")
            change_pct = data_point.get("change_pct", "")
            ticker_sym = data_point.get("ticker", ticker)
            
            ref = self._create_reference(
                source_type="market_data",
                quote=f"{ticker_sym}: {close} ({change_pct:+.2f}%)" if isinstance(change_pct, (int, float)) else f"{ticker_sym}: {close}",
                source_file=data_point.get("_source_file", "market_data.json"),
                date=date or self.briefing_date,
                ticker=ticker_sym,
            )
            references.append(ref)
        
        return {"data": results, "references": references}
    
    def _search_sec_edgar(self, args: Dict) -> Dict[str, Any]:
        """Search SEC Edgar filings."""
        query = args.get("query", "")
        form_type = args.get("form_type")
        
        if "sec_edgar" not in self._tools:
            return {"data": [], "references": [], "message": "SEC Edgar data not loaded"}
        
        results = self._tools["sec_edgar"].search(query)
        
        # Filter by form type if provided
        if form_type:
            results = [r for r in results if r.get("form_type", "").upper() == form_type.upper()]
        
        # Create references
        references = []
        for filing in results:
            ref = self._create_reference(
                source_type="sec_edgar",
                quote=f"{filing.get('company', '')} {filing.get('form_type', '')} ({filing.get('filing_date', '')})",
                source_file=filing.get("_source_file", "sec_filings.json"),
                date=filing.get("filing_date"),
                meta={
                    "cik": filing.get("cik"),
                    "accession_number": filing.get("accession_number"),
                }
            )
            references.append(ref)
        
        return {"data": results, "references": references}
    
    def _get_sources_summary(self, args: Dict) -> Dict[str, Any]:
        """Get a summary of all available sources."""
        summary = {
            "briefing_date": self.briefing_date,
            "available_sources": {},
        }
        
        for name, tool in self._tools.items():
            count = 0
            if hasattr(tool, "_data"):
                if isinstance(tool._data, list):
                    count = len(tool._data)
                elif isinstance(tool._data, dict):
                    count = len(tool._data)
            
            summary["available_sources"][name] = {
                "loaded": True,
                "count": count,
                "source_type": tool.source_type if hasattr(tool, "source_type") else name,
            }
        
        return {"data": summary, "references": []}
    
    def get_all_references(self) -> List[Dict[str, Any]]:
        """Get all references that have been created during tool calls."""
        return self._references
    
    def reset_references(self) -> None:
        """Clear the references list."""
        self._references = []


# =============================================================================
# Convenience Functions
# =============================================================================

def create_tool_executor(
    te_output_path: str = None,
    news_path: str = None,
    market_data_path: str = None,
    sec_edgar_path: str = None,
    yahoo_finance_profile: str = "jonghyun",
    briefing_date: str = None,
) -> BriefingSourceToolAdapter:
    """
    Create a tool executor with the given source paths.
    
    Args:
        te_output_path: Path to te_calendar_scraper output directory
        news_path: Path to news JSON files
        market_data_path: Path to market data files
        sec_edgar_path: Path to SEC Edgar files
        yahoo_finance_profile: AWS profile for Yahoo Finance DynamoDB
        briefing_date: Date of the briefing (YYYY-MM-DD)
        
    Returns:
        BriefingSourceToolAdapter instance
    """
    config = SourceConfig(briefing_date=briefing_date)
    
    if te_output_path:
        te_path = Path(te_output_path)
        config.te_calendar_path = te_path / "calendar" if (te_path / "calendar").exists() else None
        config.te_indicators_path = te_path / "indicators" if (te_path / "indicators").exists() else None
        config.te_fomc_path = te_path / "fomc_press_conferences" if (te_path / "fomc_press_conferences").exists() else None
    
    if news_path:
        config.news_path = Path(news_path)
    
    if market_data_path:
        config.market_data_path = Path(market_data_path)
    
    if sec_edgar_path:
        config.sec_edgar_path = Path(sec_edgar_path)
    
    config.yahoo_finance_profile = yahoo_finance_profile
    
    return BriefingSourceToolAdapter(config)


def format_tool_result_for_llm(result: Dict[str, Any]) -> str:
    """Format tool result as a string for the LLM to process."""
    if "error" in result:
        return f"Error: {result['error']}"
    
    if "message" in result and not result.get("data"):
        return f"Info: {result['message']}"
    
    data = result.get("data", [])
    
    if not data:
        return "No data found."
    
    # Format data with inline source references
    output_lines = []
    
    if isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, dict):
                # Get reference info
                source_file = item.get("_source_file", "")
                source_type = item.get("source_type", "")
                
                # Clean item for display (remove internal fields)
                display_item = {k: v for k, v in item.items() if not k.startswith("_")}
                
                item_str = json.dumps(display_item, ensure_ascii=False, indent=2)
                
                if source_file or source_type:
                    source_tag = f"[SOURCE: {source_type or 'data'}"
                    if source_file:
                        source_tag += f" | file:{source_file}"
                    source_tag += "]"
                    output_lines.append(f"{source_tag}\n{item_str}")
                else:
                    output_lines.append(item_str)
            else:
                output_lines.append(str(item))
    elif isinstance(data, dict):
        output_lines.append(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        output_lines.append(str(data))
    
    return "\n\n".join(output_lines)

