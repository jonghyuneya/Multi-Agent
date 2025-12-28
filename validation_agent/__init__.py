"""
Validation Agent - Modular Script Validation Framework

This module provides a flexible validation framework for AI-generated scripts.
It validates:
1. Source accuracy - Are all facts traceable to source data?
2. Context fitness - Is the content appropriate for the target audience?

The framework is designed to be extensible:
- Add new source tools by implementing SourceTool base class
- Add new validators by implementing Validator base class
- Configure for different AI agents (closing_briefing, etc.)

Usage:
    from validation_agent import ValidationAgent, TECalendarSourceTool
    
    agent = ValidationAgent()
    agent.register_source_tool(TECalendarSourceTool())
    
    result = agent.validate(script_text, references)

For structured briefing scripts with embedded sources:
    from validation_agent import validate_briefing_script
    
    result = validate_briefing_script(
        script_json,
        articles_path=Path("articles.json"),
        events_path=Path("events.json"),
    )
"""

__version__ = "0.1.0"

from validation_agent.base import (
    SourceTool,
    Validator,
    ValidationResult,
    SourceMatch,
    ValidationAgent,
    ValidationStatus,
    AudienceFitness,
)
from validation_agent.source_tools import (
    TECalendarSourceTool,
    TEIndicatorsSourceTool,
    FOMCSourceTool,
    NewsSourceTool,
    BriefingScriptSourceTool,
    ArticleSourceTool,
    EventSourceTool,
)
from validation_agent.validators import (
    FactValidator,
    AudienceValidator,
    CitationValidator,
)
from validation_agent.script_validator import (
    BriefingScript,
    ScriptItem,
    ScriptSource,
    ScriptSourceValidator,
    ScriptContentValidator,
    validate_briefing_script,
)

__all__ = [
    # Base classes
    "SourceTool",
    "Validator", 
    "ValidationResult",
    "SourceMatch",
    "ValidationAgent",
    "ValidationStatus",
    "AudienceFitness",
    # Source tools for te_calendar_scraper data
    "TECalendarSourceTool",
    "TEIndicatorsSourceTool",
    "FOMCSourceTool",
    "NewsSourceTool",
    # Source tools for structured briefing scripts
    "BriefingScriptSourceTool",
    "ArticleSourceTool",
    "EventSourceTool",
    # Generic validators
    "FactValidator",
    "AudienceValidator",
    "CitationValidator",
    # Script-specific validators
    "BriefingScript",
    "ScriptItem",
    "ScriptSource",
    "ScriptSourceValidator",
    "ScriptContentValidator",
    "validate_briefing_script",
]

