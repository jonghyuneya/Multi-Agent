#!/usr/bin/env python3
"""
Validation Agent - Main Entry Point

Command-line interface for validating AI-generated scripts.

Usage:
    # Validate a script file
    python -m validation_agent.main --script path/to/script.txt
    
    # Validate from stdin
    cat script.txt | python -m validation_agent.main --stdin
    
    # Output JSON result
    python -m validation_agent.main --script script.txt --output-json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List

from validation_agent.base import ValidationAgent
from validation_agent.source_tools import (
    TECalendarSourceTool,
    TEIndicatorsSourceTool,
    FOMCSourceTool,
    NewsSourceTool,
    ArticleSourceTool,
    EventSourceTool,
    BriefingScriptSourceTool,
)
from validation_agent.validators import (
    FactValidator,
    AudienceValidator,
    CitationValidator,
)
from validation_agent.script_validator import (
    ScriptSourceValidator,
    ScriptContentValidator,
    BriefingScript,
)
from validation_agent.config import DEFAULT_TE_OUTPUT_PATH

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_agent(
    te_output_path: Path = None,
    news_path: Path = None,
    articles_path: Path = None,
    events_path: Path = None,
) -> ValidationAgent:
    """
    Create and configure a validation agent with ALL validators.
    
    Args:
        te_output_path: Path to te_calendar_scraper output directory
        news_path: Path to news data (JSON files)
        articles_path: Path to articles data (for structured scripts)
        events_path: Path to events data (for structured scripts)
        
    Returns:
        Configured ValidationAgent with all source tools and validators
    """
    agent = ValidationAgent()
    
    # Register ALL source tools
    agent.register_source_tool(TECalendarSourceTool())
    agent.register_source_tool(TEIndicatorsSourceTool())
    agent.register_source_tool(FOMCSourceTool())
    agent.register_source_tool(NewsSourceTool())
    agent.register_source_tool(ArticleSourceTool())
    agent.register_source_tool(EventSourceTool())
    agent.register_source_tool(BriefingScriptSourceTool())
    
    # Register ALL validators
    agent.register_validator(FactValidator())
    agent.register_validator(AudienceValidator())
    agent.register_validator(CitationValidator())
    agent.register_validator(ScriptSourceValidator())
    agent.register_validator(ScriptContentValidator())
    
    # Load sources from all available paths
    source_paths = {}
    
    if te_output_path:
        te_path = Path(te_output_path)
        if (te_path / "calendar").exists():
            source_paths["calendar_events"] = te_path / "calendar"
        if (te_path / "indicators").exists():
            source_paths["macro_data"] = te_path / "indicators"
        if (te_path / "fomc_press_conferences").exists():
            source_paths["fomc_events"] = te_path / "fomc_press_conferences"
    
    if news_path:
        source_paths["news_data"] = Path(news_path)
    
    if articles_path:
        source_paths["article"] = Path(articles_path)
    
    if events_path:
        source_paths["event"] = Path(events_path)
    
    if source_paths:
        agent.load_sources(source_paths)
    
    return agent


def validate_script(
    script: str,
    te_output_path: Path = None,
    news_path: Path = None,
    articles_path: Path = None,
    events_path: Path = None,
    script_id: str = None,
) -> dict:
    """
    Validate a script using ALL validators.
    
    Args:
        script: The script text or JSON to validate
        te_output_path: Path to te_calendar_scraper output
        news_path: Path to news data
        articles_path: Path to articles data
        events_path: Path to events data
        script_id: Optional identifier for the script
        
    Returns:
        Validation result as dictionary
    """
    agent = create_agent(
        te_output_path=te_output_path,
        news_path=news_path,
        articles_path=articles_path,
        events_path=events_path,
    )
    result = agent.validate(script, script_id=script_id)
    return result.to_dict()


def main(args: List[str] = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate AI-generated scripts against source data. "
                   "Runs ALL validators (fact, audience, citation, source, content) automatically.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Validate a script file
    python -m validation_agent.main --script closing_script.txt
    
    # Validate with custom source paths
    python -m validation_agent.main --script script.txt \\
        --te-output /path/to/te_calendar_scraper/output
    
    # Validate structured JSON script with article/event sources
    python -m validation_agent.main --script briefing.json \\
        --articles /path/to/articles.json \\
        --events /path/to/events.json
    
    # Output JSON
    python -m validation_agent.main --script script.txt --output-json
        """,
    )
    
    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--script", "-s",
        type=Path,
        help="Path to script file to validate (text or JSON)",
    )
    input_group.add_argument(
        "--stdin",
        action="store_true",
        help="Read script from stdin",
    )
    
    # Source paths
    parser.add_argument(
        "--te-output",
        type=Path,
        default=DEFAULT_TE_OUTPUT_PATH,
        help="Path to te_calendar_scraper output directory",
    )
    parser.add_argument(
        "--news-path",
        type=Path,
        help="Path to news data (JSON files)",
    )
    parser.add_argument(
        "--articles",
        type=Path,
        help="Path to articles data for structured script validation",
    )
    parser.add_argument(
        "--events",
        type=Path,
        help="Path to events data for structured script validation",
    )
    
    # Output options
    parser.add_argument(
        "--output-json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--output-file", "-o",
        type=Path,
        help="Save results to file",
    )
    
    # Other options
    parser.add_argument(
        "--script-id",
        type=str,
        help="Identifier for the script",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )
    
    args = parser.parse_args(args)
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Read script
    if args.script:
        try:
            script = args.script.read_text(encoding="utf-8")
            script_id = args.script_id or args.script.stem
        except Exception as e:
            logger.error(f"Failed to read script file: {e}")
            return 1
    else:
        script = sys.stdin.read()
        script_id = args.script_id or "stdin"
    
    if not script.strip():
        logger.error("Empty script provided")
        return 1
    
    # Validate
    try:
        result = validate_script(
            script=script,
            te_output_path=args.te_output,
            news_path=args.news_path,
            articles_path=args.articles,
            events_path=args.events,
            script_id=script_id,
        )
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        return 1
    
    # Output results
    if args.output_json:
        output = json.dumps(result, indent=2, ensure_ascii=False)
    else:
        output = format_result_text(result)
    
    if args.output_file:
        args.output_file.write_text(output, encoding="utf-8")
        logger.info(f"Results saved to {args.output_file}")
    else:
        print(output)
    
    # Return exit code based on validation result
    return 0 if result.get("overall_valid", False) else 2


def format_result_text(result: dict) -> str:
    """Format validation result as human-readable text."""
    lines = []
    
    lines.append("=" * 60)
    lines.append(f"검증 결과: {result.get('script_id', 'Unknown')}")
    lines.append(f"검증 시각: {result.get('validated_at', '')}")
    lines.append("=" * 60)
    
    # Summary
    lines.append("\n📊 요약")
    lines.append("-" * 40)
    if result.get("summary"):
        lines.append(result["summary"])
    
    # Fact validation
    total = result.get("total_claims", 0)
    valid = result.get("valid_claims", 0)
    invalid = result.get("invalid_claims", 0)
    not_found = result.get("not_found_claims", 0)
    
    if total > 0:
        valid_pct = (valid / total) * 100
        lines.append(f"\n📋 사실 검증: {valid}/{total} ({valid_pct:.1f}%) 일치")
        if invalid > 0:
            lines.append(f"  ⚠️ 불일치: {invalid}건")
        if not_found > 0:
            lines.append(f"  ❓ 출처 미확인: {not_found}건")
        
        # Show invalid claims
        if invalid > 0:
            lines.append("\n불일치 상세:")
            for match in result.get("source_matches", []):
                if match.get("status") == "invalid":
                    lines.append(f"  - 주장: {match.get('claim', '')[:50]}...")
                    lines.append(f"    설명: {match.get('explanation', '')}")
                    if match.get("suggested_correction"):
                        lines.append(f"    제안: {match.get('suggested_correction', '')}")
    
    # Source type breakdown
    source_types = {}
    for match in result.get("source_matches", []):
        st = match.get("source_type", "unknown")
        status = match.get("status", "unknown")
        if st not in source_types:
            source_types[st] = {"valid": 0, "invalid": 0, "not_found": 0, "partial": 0}
        if status == "valid":
            source_types[st]["valid"] += 1
        elif status == "invalid":
            source_types[st]["invalid"] += 1
        elif status == "not_found":
            source_types[st]["not_found"] += 1
        elif status == "partial":
            source_types[st]["partial"] += 1
    
    if source_types:
        lines.append("\n📁 출처 유형별 검증:")
        for st, counts in source_types.items():
            total_st = sum(counts.values())
            lines.append(f"  - {st}: {counts['valid']}/{total_st} 확인, "
                        f"{counts['partial']} 부분일치, "
                        f"{counts['invalid']} 불일치, "
                        f"{counts['not_found']} 미확인")
    
    # Audience fitness
    lines.append(f"\n👥 대상 적합성: {result.get('audience_fitness', 'unknown')}")
    if result.get("audience_feedback"):
        lines.append(result["audience_feedback"])
    
    # Citations
    if not result.get("citations_complete", True):
        lines.append(f"\n📝 출처 누락: {len(result.get('missing_citations', []))}건")
        for citation in result.get("missing_citations", [])[:5]:
            lines.append(f"  - {citation[:80]}...")
    
    # Overall result
    lines.append("\n" + "=" * 60)
    overall = "✅ 통과" if result.get("overall_valid", False) else "❌ 수정 필요"
    lines.append(f"전체 결과: {overall}")
    lines.append("=" * 60)
    
    # Errors
    if result.get("errors"):
        lines.append("\n⚠️ 오류:")
        for error in result["errors"]:
            lines.append(f"  - {error}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
