"""
Main entry point for the Korean closing market briefing pipeline.

Provides the `run_closing_briefing` function and CLI interface.
"""

import argparse
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from closing_briefing.models import ClosingBriefingState
from closing_briefing.graph import build_graph, save_output
from closing_briefing.data_loader import create_sample_source_data

logger = logging.getLogger(__name__)


def run_closing_briefing(
    source_path: str,
    iterations: int = 1,
    briefing_date: Optional[str] = None,
    output_path: Optional[str] = None,
    load_news_from_dynamodb: bool = True,
    dynamodb_profile: str = "jonghyun",
) -> str:
    """
    Run the closing briefing pipeline and return the final script.
    
    Args:
        source_path: Path to source data directory or JSON bundle
        iterations: Number of critic-revision iterations (default: 1)
        briefing_date: Optional date override (YYYY-MM-DD)
        output_path: Optional path to save the output
        load_news_from_dynamodb: Whether to load news from AWS DynamoDB
        dynamodb_profile: AWS SSO profile name for DynamoDB access
        
    Returns:
        The final revised script as a string
    """
    logger.info(f"Starting closing briefing pipeline")
    logger.info(f"  Source path: {source_path}")
    logger.info(f"  Iterations: {iterations}")
    logger.info(f"  Briefing date: {briefing_date or 'auto'}")
    logger.info(f"  Load news from DynamoDB: {load_news_from_dynamodb}")
    
    # Build the graph
    app = build_graph()
    
    # Initialize state with DynamoDB configuration
    initial_state = ClosingBriefingState(
        sources={
            "_source_path": source_path,
            "_load_news_from_dynamodb": load_news_from_dynamodb,
            "_dynamodb_profile": dynamodb_profile,
        },
        max_iterations=iterations,
        briefing_date=briefing_date,
    )
    
    # Run the pipeline
    logger.info("Running pipeline...")
    final_state = app.invoke(initial_state)
    
    # Convert to ClosingBriefingState if needed
    if isinstance(final_state, dict):
        final_state = ClosingBriefingState(**final_state)
    
    # Get the final script
    final_script = final_state.script_revised or final_state.script_draft
    
    if not final_script:
        logger.error("Pipeline failed to generate a script")
        if final_state.error_message:
            logger.error(f"Error: {final_state.error_message}")
        return ""
    
    # Save output if path provided
    if output_path:
        saved_path = save_output(final_state, output_path)
        logger.info(f"Script saved to: {saved_path}")
    
    logger.info("Pipeline completed successfully")
    logger.info(f"  Keywords: {final_state.keywords}")
    logger.info(f"  Iterations completed: {final_state.iterations}")
    logger.info(f"  Script length: {len(final_script)} chars")
    
    return final_script


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate a Korean closing market briefing script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with sample data
  python -m closing_briefing.run_pipeline --create-sample --source-path data/sample_sources

  # Run with existing data
  python -m closing_briefing.run_pipeline --source-path /path/to/data

  # Run with multiple iterations
  python -m closing_briefing.run_pipeline --source-path data/sources --iterations 2

  # Run with specific date
  python -m closing_briefing.run_pipeline --source-path data/sources --date 2025-12-04
        """
    )
    
    parser.add_argument(
        "--source-path",
        type=str,
        default="data/sample_sources",
        help="Path to source data directory or JSON bundle"
    )
    
    parser.add_argument(
        "--iterations",
        type=int,
        default=1,
        choices=range(1, 11),
        metavar="{1-10}",
        help="Max critic-revision iterations (1-10, default: 1). Stops early if quality is acceptable."
    )
    
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Briefing date (YYYY-MM-DD format)"
    )
    
    parser.add_argument(
        "--output-path",
        type=str,
        default="output/closing_briefings",
        help="Directory to save output files"
    )
    
    parser.add_argument(
        "--create-sample",
        action="store_true",
        help="Create sample source data before running"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only create sample data, don't run pipeline"
    )
    
    parser.add_argument(
        "--include-news",
        action="store_true",
        default=True,
        help="Load news from AWS DynamoDB (default: True)"
    )
    
    parser.add_argument(
        "--no-news",
        action="store_true",
        help="Skip loading news from AWS DynamoDB"
    )
    
    parser.add_argument(
        "--aws-profile",
        type=str,
        default="jonghyun",
        help="AWS SSO profile name for DynamoDB access (default: jonghyun)"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create sample data if requested
    if args.create_sample:
        print(f"\n📁 Creating sample source data at: {args.source_path}")
        create_sample_source_data(args.source_path)
    
    if args.dry_run:
        print("\n✅ Dry run complete. Sample data created.")
        return
    
    # Check if source path exists
    if not Path(args.source_path).exists():
        print(f"\n❌ Error: Source path does not exist: {args.source_path}")
        print("   Use --create-sample to create sample data first.")
        return
    
    # Determine whether to load news from DynamoDB
    load_news = args.include_news and not args.no_news
    
    print("\n" + "=" * 60)
    print("🎙️  Korean Closing Market Briefing Generator")
    print("=" * 60)
    print(f"\n📂 Source: {args.source_path}")
    print(f"🔄 Iterations: {args.iterations}")
    print(f"📅 Date: {args.date or 'Auto-detect'}")
    print(f"💾 Output: {args.output_path}")
    print(f"📰 Load news from DynamoDB: {load_news}")
    if load_news:
        print(f"🔑 AWS Profile: {args.aws_profile}")
    print()
    
    try:
        # Run the pipeline
        script = run_closing_briefing(
            source_path=args.source_path,
            iterations=args.iterations,
            briefing_date=args.date,
            output_path=args.output_path,
            load_news_from_dynamodb=load_news,
            dynamodb_profile=args.aws_profile,
        )
        
        if script:
            print("\n" + "=" * 60)
            print("✅ Script Generated Successfully!")
            print("=" * 60)
            print(f"\n📝 Script Preview (first 1000 chars):\n")
            print("-" * 40)
            print(script[:1000])
            if len(script) > 1000:
                print(f"\n... ({len(script) - 1000} more characters)")
            print("-" * 40)
            print(f"\n💾 Full script saved to: {args.output_path}")
        else:
            print("\n❌ Failed to generate script. Check logs for details.")
            
    except Exception as e:
        logger.exception("Pipeline failed with error")
        print(f"\n❌ Error: {str(e)}")
        raise


if __name__ == "__main__":
    main()

