"""
Korean Closing Market Briefing Generator

A LangGraph-based multi-agent system that generates a Korean closing market briefing script
in the style of a radio/podcast dialogue between two participants (진행자 and 해설자),
with a critic and iterative refinement.

Usage:
    from closing_briefing import run_closing_briefing
    
    script = run_closing_briefing(
        source_path="data/sources",
        iterations=1,
        briefing_date="2025-12-04"
    )
    print(script)

CLI Usage:
    python -m closing_briefing.run_pipeline --source-path data/sources --iterations 1
"""

__version__ = "0.1.0"

from closing_briefing.run_pipeline import run_closing_briefing
from closing_briefing.models import ClosingBriefingState, BriefingConfig, Reference
from closing_briefing.data_loader import (
    ClosingBriefingDataLoader,
    EconBriefingDataLoader,
    DynamoDBNewsLoader,
    create_sample_source_data,
)
from closing_briefing.graph import build_graph
from closing_briefing.tools import BRIEFING_TOOLS, DataToolExecutor

__all__ = [
    "run_closing_briefing",
    "ClosingBriefingState",
    "BriefingConfig",
    "Reference",
    "ClosingBriefingDataLoader",
    "EconBriefingDataLoader",
    "DynamoDBNewsLoader",
    "create_sample_source_data",
    "build_graph",
    "BRIEFING_TOOLS",
    "DataToolExecutor",
]

