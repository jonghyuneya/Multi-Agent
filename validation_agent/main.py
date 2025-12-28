#!/usr/bin/env python3
"""
Validation Agent - Main Entry Point

Command-line interface for validating AI-generated scripts.

Usage:
    # Validate a script file
    python -m validation_agent.main --script path/to/script.txt
    
    # Validate from stdin
    cat script.txt | python -m validation_agent.main --stdin
    
    # Validate with specific validators only
    python -m validation_agent.main --script script.txt --validators fact citation
    
    # Output JSON result
    python -m validation_agent.main --script script.txt --output-json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Optional

from validation_agent.base import ValidationAgent
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
from validation_agent.config import ValidationConfig, DEFAULT_TE_OUTPUT_PATH

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_agent(config: ValidationConfig) -> ValidationAgent:
    """Create and configure a validation agent."""
    agent = ValidationAgent()
    
    # Register source tools
    agent.register_source_tool(TECalendarSourceTool())
    agent.register_source_tool(TEIndicatorsSourceTool())
    agent.register_source_tool(FOMCSourceTool())
    
    if config.news_path:
        agent.register_source_tool(NewsSourceTool())
    
    # Register validators
    if "fact" in config.validators:
        agent.register_validator(FactValidator())
    if "audience" in config.validators:
        agent.register_validator(AudienceValidator())
    if "citation" in config.validators:
        agent.register_validator(CitationValidator())
    
    # Load sources
    agent.load_sources(config.get_source_paths())
    
    return agent


def validate_script(
    script: str,
    config: ValidationConfig,
    script_id: str = None,
) -> dict:
    """
    Validate a script and return results.
    
    Args:
        script: The script text to validate
        config: Validation configuration
        script_id: Optional identifier for the script
        
    Returns:
        Validation result as dictionary
    """
    agent = create_agent(config)
    result = agent.validate(script, script_id=script_id)
    return result.to_dict()


def main(args: List[str] = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate AI-generated scripts against source data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Validate a script file
    python -m validation_agent.main --script closing_script.txt
    
    # Validate with only fact checking
    python -m validation_agent.main --script script.txt --validators fact
    
    # Output JSON
    python -m validation_agent.main --script script.txt --output-json
    
    # Custom source paths
    python -m validation_agent.main --script script.txt \\
        --te-output /path/to/te_calendar_scraper/output
        """,
    )
    
    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--script", "-s",
        type=Path,
        help="Path to script file to validate",
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
    
    # Validator options
    parser.add_argument(
        "--validators",
        nargs="+",
        choices=["fact", "audience", "citation"],
        default=["fact", "audience", "citation"],
        help="Validators to run (default: all)",
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
    
    # Create configuration
    config = ValidationConfig(
        calendar_path=args.te_output / "calendar",
        indicators_path=args.te_output / "indicators",
        fomc_path=args.te_output / "fomc_press_conferences",
        news_path=args.news_path,
        validators=args.validators,
    )
    
    # Validate
    try:
        result = validate_script(script, config, script_id)
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
    lines.append(f"Validation Result: {result.get('script_id', 'Unknown')}")
    lines.append(f"Validated at: {result.get('validated_at', '')}")
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
        lines.append(f"\n📋 사실 검증: {valid}/{total} 일치")
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

