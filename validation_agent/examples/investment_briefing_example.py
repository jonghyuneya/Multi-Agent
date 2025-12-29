#!/usr/bin/env python3
"""
Example: Validating Investment Briefing Scripts

This example demonstrates how to validate investment briefing scripts
that contain embedded source references (SEC filings, news articles, market data).

The investment briefing format includes:
- ticker: Stock symbol
- rounds: Debate rounds with fundamental, risk, growth, sentiment analysis
- conclusion: Final recommendation
- sources: {sec_filings, news_articles, market_data}
"""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from validation_agent import (
    ValidationAgent,
    InvestmentBriefingSourceValidator,
    InvestmentBriefingContentValidator,
    validate_investment_briefing,
)


def main():
    """Run investment briefing validation example."""
    
    print("=" * 70)
    print("Investment Briefing Validation Example")
    print("=" * 70)
    
    # Example: Load a briefing file
    example_file = Path("/home/jhkim/econ_briefing/output/briefing_result.json")
    
    if not example_file.exists():
        print(f"Example file not found: {example_file}")
        print("\nUsing inline sample data instead...")
        
        # Sample investment briefing structure
        sample_briefing = {
            "ticker": "GOOG",
            "timestamp": "20251228_151414",
            "rounds": [
                {
                    "round": 1,
                    "fundamental": "영업마진 30.5%를 유지하며 재무 체력이 견조합니다. (2025-10-30 제출 10-Q 기준)",
                    "risk": "AI CAPEX 증가로 단기 마진 압박 가능성이 있습니다.",
                    "growth": "Google Cloud 성장률이 YoY 25% 이상입니다.",
                    "sentiment": "뉴스 ID 8 ('Google started the year behind...')에서 AI 경쟁력 회복 평가"
                }
            ],
            "conclusion": "HOLD 의견. 2025-10-30 제출된 10-Q에서 영업마진 30%대 유지 확인.",
            "readable_summary": "GOOG: HOLD",
            "debate_transcript": "",
            "sources": {
                "ticker": "GOOG",
                "collected_at": "2025-12-28T06:12:52.573149+00:00",
                "sec_filings": [
                    {
                        "form": "10-Q",
                        "filed_date": "2025-10-30",
                        "reporting_for": "2025-09-30",
                        "accession_number": "0001652044-25-000091",
                        "file_path": "downloads/sec_filings/..."
                    },
                    {
                        "form": "10-K",
                        "filed_date": "2025-02-05",
                        "reporting_for": "2024-12-31",
                        "accession_number": "0001652044-25-000014",
                        "file_path": "downloads/sec_filings/..."
                    }
                ],
                "news_articles": [
                    {
                        "id": 7,
                        "title": "Google Cloud chief reveals the long game...",
                        "published_at": "2025-12-23T11:30:04.772950-05:00",
                        "source": "Yahoo Finance"
                    },
                    {
                        "id": 8,
                        "title": "Google started the year behind in the AI race...",
                        "published_at": "2025-12-23T10:30:03.962835-05:00",
                        "source": "Yahoo Finance"
                    }
                ],
                "market_data": {
                    "source": "yfinance",
                    "fetched_at": "2025-12-28T06:12:52.573184+00:00",
                    "current_price": 314.96,
                    "pe_ratio": 31.061142,
                    "market_cap": 3802144702464.0
                }
            },
            "structured_conclusion": {
                "action": "HOLD",
                "position_size": 10
            }
        }
        
        script_json = json.dumps(sample_briefing, ensure_ascii=False)
    else:
        print(f"Loading briefing from: {example_file}")
        with open(example_file, "r", encoding="utf-8") as f:
            script_json = f.read()
    
    print()
    
    # Method 1: Using the convenience function (simple)
    print("-" * 50)
    print("Method 1: Using validate_investment_briefing()")
    print("-" * 50)
    
    result = validate_investment_briefing(
        script_json,
        validate_content=False  # Skip LLM-based content validation to save API calls
    )
    
    print(f"\n📊 Validation Result:")
    print(f"   Overall Valid: {result.overall_valid}")
    print(f"   Total Claims: {result.total_claims}")
    print(f"   Valid Claims: {result.valid_claims}")
    print(f"   Not Found: {result.not_found_claims}")
    print(f"   Invalid: {result.invalid_claims}")
    
    if result.summary:
        print(f"\n📝 Summary:\n{result.summary}")
    
    if result.source_matches:
        print(f"\n🔍 Source Matches:")
        for match in result.source_matches[:10]:  # Show first 10
            status_emoji = {
                "VALID": "✅",
                "PARTIAL": "⚠️",
                "INVALID": "❌",
                "NOT_FOUND": "❓",
            }.get(match.status.name, "❓")
            print(f"   {status_emoji} [{match.source_type}] {match.claim[:60]}...")
            print(f"       → {match.explanation}")
    
    # Method 2: Using ValidationAgent directly (more control)
    print()
    print("-" * 50)
    print("Method 2: Using ValidationAgent with custom setup")
    print("-" * 50)
    
    agent = ValidationAgent()
    
    # Register only source validator (skip content for speed)
    source_validator = InvestmentBriefingSourceValidator()
    agent.register_validator(source_validator)
    
    result2 = agent.validate(script_json)
    
    print(f"\n📊 Validation Result:")
    print(f"   Overall Valid: {result2.overall_valid}")
    print(f"   Validators Run: {len(agent._validators)}")
    
    if result2.errors:
        print(f"\n❌ Errors:")
        for error in result2.errors:
            print(f"   - {error}")
    
    print()
    print("=" * 70)
    print("Validation Complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()

