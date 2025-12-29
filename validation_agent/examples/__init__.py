"""
Example configurations for the Validation Agent.

This module provides ready-to-use configurations for validating
different AI agent outputs.
"""

from validation_agent.examples.closing_briefing_validator import (
    ClosingBriefingValidator,
    create_closing_briefing_validator,
)

__all__ = [
    "ClosingBriefingValidator",
    "create_closing_briefing_validator",
]

