"""
Tool definitions for the Korean closing market briefing pipeline.

Provides data access tools that the LLM can call to retrieve specific information
from the loaded sources. Each tool returns data with exact source references.
"""

import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================================
# Tool Definitions for OpenAI Function Calling
# ============================================================================

BRIEFING_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_macro_indicators",
            "description": "Retrieve macroeconomic indicators (CPI, PMI, yields, etc.). Use this to get exact values for macro data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "indicator_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of specific indicator names to filter (e.g., ['CPI YoY', 'US 10Y Yield']). If empty, returns all."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_calendar_events",
            "description": "Retrieve upcoming economic calendar events. Use this to get exact event names, dates, and times.",
            "parameters": {
                "type": "object",
                "properties": {
                    "importance": {
                        "type": "string",
                        "enum": ["high", "medium", "low", "all"],
                        "description": "Filter by importance level. Default is 'all'."
                    },
                    "days_ahead": {
                        "type": "integer",
                        "description": "Number of days ahead to look. Default is 14."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_news_articles",
            "description": "Retrieve news articles with headlines and sources. Use this to get exact headlines and provider names.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["macro", "company", "sector", "geopolitical", "all"],
                        "description": "Filter by news category. Default is 'all'."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of articles to return. Default is 10."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_earnings_results",
            "description": "Retrieve company earnings results with EPS, revenue, and beat/miss status. Use this for exact earnings numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {
                        "type": "string",
                        "description": "Optional sector filter (e.g., 'Technology', 'Healthcare')."
                    },
                    "beat_only": {
                        "type": "boolean",
                        "description": "If true, only return companies that beat estimates."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_fomc_events",
            "description": "Retrieve FOMC meeting and press conference information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_snippets": {
                        "type": "boolean",
                        "description": "Whether to include text snippets from press conferences."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_summary",
            "description": "Retrieve market indices, sector performance, and key metrics (VIX, dollar index, yields).",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_sectors": {
                        "type": "boolean",
                        "description": "Whether to include sector breakdown. Default is true."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_data",
            "description": "Search across all data sources for specific keywords or topics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g., 'Fed', 'NVIDIA', 'inflation')."
                    }
                },
                "required": ["query"]
            }
        }
    }
]


# ============================================================================
# Tool Implementation Functions
# ============================================================================

class DataToolExecutor:
    """
    Executes tool calls against loaded source data.
    Returns data with exact source references for citation.
    """
    
    def __init__(self, sources: Dict[str, Any], briefing_date: str = None):
        """
        Initialize with loaded source data.
        
        Args:
            sources: Dictionary of loaded source data from ClosingBriefingDataLoader
            briefing_date: The date of the briefing (YYYY-MM-DD)
        """
        self.sources = sources
        self.briefing_date = briefing_date or datetime.now().strftime('%Y-%m-%d')
        
        # Track all references used
        self.references_used: List[Dict[str, Any]] = []
    
    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool call and return results with references.
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments
            
        Returns:
            Dictionary with 'data' and 'references' keys
        """
        tool_map = {
            "get_macro_indicators": self._get_macro_indicators,
            "get_calendar_events": self._get_calendar_events,
            "get_news_articles": self._get_news_articles,
            "get_earnings_results": self._get_earnings_results,
            "get_fomc_events": self._get_fomc_events,
            "get_market_summary": self._get_market_summary,
            "search_data": self._search_data,
        }
        
        if tool_name not in tool_map:
            return {"error": f"Unknown tool: {tool_name}", "references": []}
        
        try:
            result = tool_map[tool_name](arguments)
            return result
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            return {"error": str(e), "references": []}
    
    def _create_reference(
        self,
        source_type: str,
        source_file: str,
        quote: str,
        provider: str = None,
        date: str = None,
        meta: Dict = None
    ) -> Dict[str, Any]:
        """Create a standardized reference object."""
        ref = {
            "source_type": source_type,
            "source_file": source_file,
            "quote": quote,
            "provider": provider,
            "date": date or self.briefing_date,
            "meta": meta or {}
        }
        self.references_used.append(ref)
        return ref
    
    def _get_macro_indicators(self, args: Dict) -> Dict[str, Any]:
        """Get macro indicators with references."""
        macro_data = self.sources.get('macro_data', [])
        indicator_names = args.get('indicator_names', [])
        
        results = []
        references = []
        
        for indicator in macro_data:
            name = indicator.get('name', '')
            
            # Filter if specific names requested
            if indicator_names and not any(n.lower() in name.lower() for n in indicator_names):
                continue
            
            value = indicator.get('value', indicator.get('values', [None])[0])
            unit = indicator.get('unit', '')
            date = indicator.get('date', indicator.get('dates', [''])[0])
            
            # Create quote for reference
            quote = f"{name}: {value}{unit}"
            if date:
                quote += f", {date}"
            
            ref = self._create_reference(
                source_type="macro_data",
                source_file="indicators_US.csv",
                quote=quote,
                date=date,
                meta=indicator.get('meta', {})
            )
            
            results.append({
                "name": name,
                "value": value,
                "unit": unit,
                "date": date,
                "meta": indicator.get('meta', {}),
                "reference": ref
            })
            references.append(ref)
        
        return {"data": results, "references": references}
    
    def _get_calendar_events(self, args: Dict) -> Dict[str, Any]:
        """Get calendar events with references."""
        calendar_events = self.sources.get('calendar_events', [])
        importance = args.get('importance', 'all')
        days_ahead = args.get('days_ahead', 14)
        
        results = []
        references = []
        
        # Calculate date range
        try:
            base_date = datetime.strptime(self.briefing_date, '%Y-%m-%d')
        except:
            base_date = datetime.now()
        
        for event in calendar_events:
            # Filter by importance
            event_importance = event.get('importance', 'medium')
            if importance != 'all' and event_importance != importance:
                continue
            
            # Filter by date range
            event_date_str = event.get('date', '')
            if event_date_str:
                try:
                    event_date = datetime.strptime(event_date_str, '%Y-%m-%d')
                    if (event_date - base_date).days > days_ahead:
                        continue
                    if event_date < base_date:
                        continue
                except:
                    pass
            
            name = event.get('name', '')
            time = event.get('time', '')
            
            # Create quote for reference
            quote = f"{name}, {event_date_str}"
            if time:
                quote += f", {time}"
            if event_importance:
                quote += f", importance: {event_importance}"
            
            ref = self._create_reference(
                source_type="calendar_events",
                source_file="calendar_US.csv",
                quote=quote,
                date=event_date_str,
                meta=event.get('meta', {})
            )
            
            results.append({
                "name": name,
                "date": event_date_str,
                "time": time,
                "importance": event_importance,
                "description": event.get('description', ''),
                "category": event.get('category', ''),
                "reference": ref
            })
            references.append(ref)
        
        # Sort by date
        results.sort(key=lambda x: x.get('date', ''))
        
        return {"data": results, "references": references}
    
    def _get_news_articles(self, args: Dict) -> Dict[str, Any]:
        """Get news articles with references."""
        news_data = self.sources.get('news_data', [])
        category = args.get('category', 'all')
        limit = args.get('limit', 10)
        
        results = []
        references = []
        
        for article in news_data[:limit * 2]:  # Get more to allow filtering
            # Filter by category
            article_category = article.get('category', 'sector')
            if category != 'all' and article_category != category:
                continue
            
            headline = article.get('headline', '')
            provider = article.get('source', 'Unknown')
            published_date = article.get('published_date', self.briefing_date)
            
            if not headline:
                continue
            
            # Create quote for reference
            quote = f'"{headline}"'
            
            ref = self._create_reference(
                source_type="news_data",
                source_file="news_articles.json",
                quote=quote,
                provider=provider,
                date=published_date,
                meta={
                    "url": article.get('url', ''),
                    "tickers": article.get('tickers', []),
                    "tags": article.get('tags', [])
                }
            )
            
            results.append({
                "headline": headline,
                "provider": provider,
                "category": article_category,
                "summary": article.get('summary', ''),
                "market_impact": article.get('market_impact', ''),
                "tags": article.get('tags', []),
                "tickers": article.get('tickers', []),
                "published_date": published_date,
                "reference": ref
            })
            references.append(ref)
            
            if len(results) >= limit:
                break
        
        return {"data": results, "references": references}
    
    def _get_earnings_results(self, args: Dict) -> Dict[str, Any]:
        """Get earnings results with references."""
        earnings_data = self.sources.get('earnings_data', [])
        sector = args.get('sector')
        beat_only = args.get('beat_only', False)
        
        results = []
        references = []
        
        for earning in earnings_data:
            # Filter by sector
            if sector and earning.get('sector', '').lower() != sector.lower():
                continue
            
            # Filter by beat/miss
            if beat_only and earning.get('beat_or_miss') != 'beat':
                continue
            
            company = earning.get('company_name', '')
            ticker = earning.get('ticker', '')
            eps_actual = earning.get('eps_actual')
            eps_estimate = earning.get('eps_estimate')
            revenue_actual = earning.get('revenue_actual')
            revenue_estimate = earning.get('revenue_estimate')
            beat_or_miss = earning.get('beat_or_miss', '')
            
            # Format revenue for display
            def format_revenue(val):
                if val is None:
                    return None
                if val >= 1e9:
                    return f"${val/1e9:.1f}B"
                elif val >= 1e6:
                    return f"${val/1e6:.1f}M"
                return f"${val:.0f}"
            
            # Create quote for reference
            parts = [f"{company}"]
            if ticker:
                parts[0] = f"{company} ({ticker})"
            if eps_actual is not None:
                parts.append(f"EPS ${eps_actual:.2f}")
            if revenue_actual is not None:
                parts.append(f"Revenue {format_revenue(revenue_actual)}")
            if beat_or_miss:
                parts.append(f"{beat_or_miss} estimates")
            
            quote = ", ".join(parts)
            
            ref = self._create_reference(
                source_type="earnings_data",
                source_file="earnings_data.json",
                quote=quote,
                date=self.briefing_date,
                meta={
                    "sector": earning.get('sector', ''),
                    "key_drivers": earning.get('key_drivers', []),
                    "stock_reaction": earning.get('stock_reaction', '')
                }
            )
            
            results.append({
                "company_name": company,
                "ticker": ticker,
                "eps_actual": eps_actual,
                "eps_estimate": eps_estimate,
                "revenue_actual": revenue_actual,
                "revenue_estimate": revenue_estimate,
                "revenue_formatted": format_revenue(revenue_actual),
                "yoy_growth_pct": earning.get('yoy_growth_pct'),
                "beat_or_miss": beat_or_miss,
                "sector": earning.get('sector', ''),
                "key_drivers": earning.get('key_drivers', []),
                "stock_reaction": earning.get('stock_reaction', ''),
                "reference": ref
            })
            references.append(ref)
        
        return {"data": results, "references": references}
    
    def _get_fomc_events(self, args: Dict) -> Dict[str, Any]:
        """Get FOMC events with references."""
        fomc_events = self.sources.get('fomc_events', [])
        include_snippets = args.get('include_snippets', True)
        
        results = []
        references = []
        
        for event in fomc_events:
            title = event.get('title', '')
            date = event.get('date', '')
            snippet = event.get('text_snippet', '') if include_snippets else ''
            
            # Create quote for reference
            quote = f"{title}, {date}"
            
            ref = self._create_reference(
                source_type="fomc_events",
                source_file="fomc_press_conferences/",
                quote=quote,
                date=date,
                meta=event.get('meta', {})
            )
            
            result = {
                "title": title,
                "date": date,
                "type": event.get('type', 'press_conference'),
                "reference": ref
            }
            
            if include_snippets and snippet:
                result["text_snippet"] = snippet
            
            results.append(result)
            references.append(ref)
        
        # Sort by date (most recent first)
        results.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        return {"data": results, "references": references}
    
    def _get_market_summary(self, args: Dict) -> Dict[str, Any]:
        """Get market summary with references."""
        market_summary = self.sources.get('market_summary', {})
        include_sectors = args.get('include_sectors', True)
        
        if not market_summary:
            return {"data": None, "references": []}
        
        references = []
        
        # Create reference for indices
        indices = market_summary.get('indices', {})
        indices_quotes = []
        for name, data in indices.items():
            if isinstance(data, dict):
                close = data.get('close', 0)
                change_pct = data.get('change_pct', 0)
                indices_quotes.append(f"{name}: {close:.2f} ({change_pct:+.2f}%)")
        
        if indices_quotes:
            ref = self._create_reference(
                source_type="market_summary",
                source_file="market_summary.json",
                quote="; ".join(indices_quotes[:3]),
                date=market_summary.get('date', self.briefing_date)
            )
            references.append(ref)
        
        result = {
            "date": market_summary.get('date', self.briefing_date),
            "indices": indices,
            "vix": market_summary.get('vix'),
            "dollar_index": market_summary.get('dollar_index'),
            "us_10y_yield": market_summary.get('us_10y_yield'),
            "crude_oil_wti": market_summary.get('crude_oil_wti'),
            "gold": market_summary.get('gold'),
        }
        
        if include_sectors:
            result["sectors"] = market_summary.get('sectors', {})
        
        return {"data": result, "references": references}
    
    def _search_data(self, args: Dict) -> Dict[str, Any]:
        """Search across all data sources."""
        query = args.get('query', '').lower()
        
        if not query:
            return {"data": [], "references": []}
        
        results = []
        references = []
        
        # Search macro data
        for indicator in self.sources.get('macro_data', []):
            if query in indicator.get('name', '').lower():
                tool_result = self._get_macro_indicators({'indicator_names': [indicator.get('name')]})
                results.extend(tool_result.get('data', []))
                references.extend(tool_result.get('references', []))
        
        # Search news
        for article in self.sources.get('news_data', []):
            headline = article.get('headline', '').lower()
            tags = ' '.join(article.get('tags', [])).lower()
            tickers = ' '.join(article.get('tickers', [])).lower()
            
            if query in headline or query in tags or query in tickers:
                # Get individual reference
                headline_actual = article.get('headline', '')
                provider = article.get('source', 'Unknown')
                ref = self._create_reference(
                    source_type="news_data",
                    source_file="news_articles.json",
                    quote=f'"{headline_actual}"',
                    provider=provider,
                    date=article.get('published_date', self.briefing_date)
                )
                results.append({
                    "type": "news",
                    "headline": headline_actual,
                    "provider": provider,
                    "reference": ref
                })
                references.append(ref)
        
        # Search earnings
        for earning in self.sources.get('earnings_data', []):
            company = earning.get('company_name', '').lower()
            ticker = earning.get('ticker', '').lower()
            
            if query in company or query in ticker:
                tool_result = self._get_earnings_results({'sector': None})
                for item in tool_result.get('data', []):
                    if query in item.get('company_name', '').lower() or query in item.get('ticker', '').lower():
                        results.append({"type": "earnings", **item})
                        references.extend(tool_result.get('references', []))
                        break
        
        # Search calendar events
        for event in self.sources.get('calendar_events', []):
            if query in event.get('name', '').lower():
                name = event.get('name', '')
                date = event.get('date', '')
                ref = self._create_reference(
                    source_type="calendar_events",
                    source_file="calendar_US.csv",
                    quote=f"{name}, {date}",
                    date=date
                )
                results.append({
                    "type": "calendar",
                    "name": name,
                    "date": date,
                    "reference": ref
                })
                references.append(ref)
        
        return {"data": results, "references": references}
    
    def get_all_references(self) -> List[Dict[str, Any]]:
        """Get all references that have been used."""
        return self.references_used
    
    def format_references_for_output(self) -> str:
        """Format all used references as a markdown section."""
        if not self.references_used:
            return ""
        
        lines = ["## 참고 자료 (References)", ""]
        
        # Group by source type
        by_type: Dict[str, List[Dict]] = {}
        for ref in self.references_used:
            source_type = ref.get('source_type', 'unknown')
            if source_type not in by_type:
                by_type[source_type] = []
            by_type[source_type].append(ref)
        
        type_labels = {
            "macro_data": "📊 거시경제 지표",
            "calendar_events": "📅 경제 일정",
            "news_data": "📰 뉴스",
            "earnings_data": "💰 실적 발표",
            "fomc_events": "🏛️ FOMC",
            "market_summary": "📈 시장 요약"
        }
        
        for source_type, refs in by_type.items():
            label = type_labels.get(source_type, source_type)
            lines.append(f"### {label}")
            
            seen_quotes = set()
            for ref in refs:
                quote = ref.get('quote', '')
                if quote in seen_quotes:
                    continue
                seen_quotes.add(quote)
                
                line = f"- {quote}"
                if ref.get('provider'):
                    line += f" — {ref['provider']}"
                if ref.get('date'):
                    line += f" ({ref['date']})"
                lines.append(line)
            
            lines.append("")
        
        return "\n".join(lines)


def format_tool_result_for_llm(result: Dict[str, Any]) -> str:
    """Format tool result as a string for the LLM to process."""
    if "error" in result:
        return f"Error: {result['error']}"
    
    data = result.get('data', [])
    references = result.get('references', [])
    
    if not data:
        return "No data found."
    
    # Format data with inline references
    output_lines = []
    
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                ref = item.pop('reference', None)
                item_str = json.dumps(item, ensure_ascii=False, indent=2)
                if ref:
                    source_tag = f"[SOURCE: {ref['source_type']} | \"{ref['quote']}\""
                    if ref.get('provider'):
                        source_tag += f" - {ref['provider']}"
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

