"""CLI orchestrator for the TradingEconomics U.S. calendar scraper."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List

import pytz
from dataclasses import asdict

PROJECT_ROOT = Path(__file__).resolve().parent
PARENT_ROOT = PROJECT_ROOT.parent

if str(PARENT_ROOT) not in sys.path:
    sys.path.insert(0, str(PARENT_ROOT))

from te_calendar_scraper import config  # noqa: E402
from te_calendar_scraper.io import parse_output, save_csv  # noqa: E402
from te_calendar_scraper.scraper import (  # noqa: E402
    calendar_dom,
    calendar_xhr,
    download_utils,
    fomc_scraper,
    indicators_dom,
    parse_utils,
    playwright_driver,
    speeches_scraper,
)
from te_calendar_scraper.scraper.models import CalendarRow, IndicatorRow  # noqa: E402


def date_window_kst() -> tuple[datetime, datetime]:
    """Return start/end datetime objects for the rolling window in KST."""
    tz_kst = pytz.timezone(config.TZ_DISPLAY)
    now_kst = datetime.now(tz_kst)
    start = (now_kst - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = (now_kst + timedelta(days=7)).replace(hour=23, minute=59, second=59, microsecond=0)
    return start, end


def filter_rows(rows: Iterable[CalendarRow]) -> List[dict]:
    """Filter rows for the US calendar and impact levels within the desired window."""
    start_kst, end_kst = date_window_kst()
    filtered = []
    for row in rows:
        if row.country and row.country != config.COUNTRY:
            continue
        if row.impact and row.impact not in config.IMPACT_ALLOWED:
            continue
        dt_kst = row.dt_kst or parse_utils.to_kst(row.dt_utc)
        if not dt_kst or not (start_kst <= dt_kst <= end_kst):
            continue
        filtered.append(
            {
                "datetime_utc": row.dt_utc,
                "datetime_kst": dt_kst,
                "title": row.title,
                "category": row.category,
                "impact": row.impact,
                "country": row.country,
                "raw_time_text": row.raw_time_text,
                "source_url": row.source_url,
            }
        )
    return filtered


async def run_dom_mode() -> List[dict]:
    async with playwright_driver.with_browser() as browser:
        async with playwright_driver.with_context(browser) as context:
            page = await playwright_driver.new_page(context)
            await calendar_dom.goto_calendar(page)
            start_kst_dt, end_kst_dt = date_window_kst()
            await calendar_dom.apply_filters(
                page,
                config.COUNTRY,
                start_kst_dt.date(),
                end_kst_dt.date(),
                config.IMPACT_ALLOWED,
            )
            await calendar_dom.load_all_rows(page)
            raw_rows = await calendar_dom.extract_rows_from_dom(page)
    return filter_rows(raw_rows)


async def run_xhr_mode() -> List[dict]:
    async with playwright_driver.with_browser() as browser:
        async with playwright_driver.with_context(browser) as context:
            page = await playwright_driver.new_page(context)
            await calendar_dom.goto_calendar(page)
            url_template, _ = await calendar_xhr.discover_calendar_xhr(page)

    start_kst_dt, end_kst_dt = date_window_kst()
    cookies = calendar_xhr.build_cookie_payload(
        config.COUNTRY,
        start_kst_dt.date(),
        end_kst_dt.date(),
        config.IMPACT_ALLOWED,
    )
    raw_rows = calendar_xhr.fetch_calendar_rows(url_template, cookies)
    return filter_rows(raw_rows)


async def run_fomc_mode() -> None:
    """Scrape recent FOMC press conference transcripts and download PDFs."""
    # Use the simplified synchronous scraper (no Playwright needed)
    transcripts = fomc_scraper.scrape_fomc_calendar()
    
    if not transcripts:
        raise SystemExit("No FOMC transcripts found.")
    
    print(f"\nFound {len(transcripts)} recent FOMC press conference transcripts")
    print(f"Downloading to: {config.FOMC_DOWNLOADS_DIR}\n")
    
    # Download the transcripts
    stats = fomc_scraper.download_recent_transcripts(transcripts)
    
    print(f"\nFOMC Downloads Summary:")
    print(f"  Downloaded: {stats['downloaded']}")
    print(f"  Skipped (already exists): {stats['skipped']}")
    print(f"  Failed: {stats['failed']}")
    print(f"  Output directory: {config.FOMC_DOWNLOADS_DIR}")




async def run_speeches_mode() -> None:
    """Scrape Federal Reserve speeches and download HTML transcript pages."""
    async with playwright_driver.with_browser() as browser:
        async with playwright_driver.with_context(browser) as context:
            page = await playwright_driver.new_page(context)
            speeches = await speeches_scraper.scrape_speeches(page)
    
    if not speeches:
        raise SystemExit("No speeches found.")
    
    print(f"Found {len(speeches)} speeches")
    
    downloaded = 0
    skipped = 0
    failed = 0
    
    for speech in speeches:
        if not speech.transcript_url:
            print(f"Skipping '{speech.title}' - no transcript URL")
            continue
        
        # Generate filename from speech metadata
        filename_parts = []
        if speech.date:
            # Extract date part if available
            date_part = speech.date.replace('/', '_').replace('-', '_')[:10]
            filename_parts.append(date_part)
        
        # Add speaker name if available
        if speech.speaker:
            speaker_clean = speech.speaker.replace(' ', '_').replace(',', '').replace('.', '')[:30]
            filename_parts.append(speaker_clean)
        
        # Add title (cleaned)
        if speech.title:
            title_clean = ''.join(c if c.isalnum() or c in (' ', '-', '_') else '' for c in speech.title)
            title_clean = title_clean.replace(' ', '_')[:50]
            filename_parts.append(title_clean)
        
        if filename_parts:
            filename = '_'.join(filename_parts) + '.html'
        else:
            filename = download_utils.get_filename_from_url(speech.transcript_url, "speech_transcript.html")
            # Ensure .html extension
            if not filename.endswith('.html'):
                filename = filename.rsplit('.', 1)[0] + '.html'
        
        # Check if file already exists
        existing_file = config.SPEECHES_DOWNLOADS_DIR / filename
        if existing_file.exists():
            skipped += 1
            print(f"Skipped (exists): {speech.title[:60]}")
            continue
        
        # Download HTML content (not PDF)
        result = download_utils.download_html_file(
            speech.transcript_url,
            config.SPEECHES_DOWNLOADS_DIR,
            filename,
            skip_existing=True,
        )
        
        if result and result.exists() and result.stat().st_size > 0:
            downloaded += 1
            print(f"Downloaded: {speech.title[:60]}")
        else:
            failed += 1
            print(f"Failed: {speech.title[:60]}")
    
    print(f"\nSpeeches Downloads Summary:")
    print(f"  Downloaded: {downloaded}")
    print(f"  Skipped (already exists): {skipped}")
    print(f"  Failed: {failed}")
    print(f"  Output directory: {config.SPEECHES_DOWNLOADS_DIR}")


async def run_parse_output_mode() -> None:
    """Parse and display summary of output calendar and indicator files."""
    print("=" * 60)
    print("Parsing Output Files")
    print("=" * 60)
    
    # Parse calendar files
    print("\n📅 Calendar Files:")
    calendar_files = parse_output.list_calendar_files()
    if calendar_files:
        print(f"Found {len(calendar_files)} calendar file(s)")
        for i, file_path in enumerate(calendar_files[:5], 1):  # Show top 5
            print(f"  {i}. {file_path.name}")
            try:
                df = parse_output.parse_calendar_csv(file_path)
                summary = parse_output.get_calendar_summary(df)
                print(f"     Entries: {summary['total_entries']}")
                if summary['date_range']:
                    print(f"     Date Range: {summary['date_range']['start']} to {summary['date_range']['end']}")
                if summary['categories']:
                    top_cat = max(summary['categories'].items(), key=lambda x: x[1])
                    print(f"     Top Category: {top_cat[0]} ({top_cat[1]} entries)")
            except Exception as e:
                print(f"     Error parsing: {e}")
    else:
        print("  No calendar files found")
    
    # Parse indicator files
    print("\n📊 Indicator Files:")
    indicator_files = parse_output.list_indicator_files()
    if indicator_files:
        print(f"Found {len(indicator_files)} indicator file(s)")
        for i, file_path in enumerate(indicator_files[:5], 1):  # Show top 5
            print(f"  {i}. {file_path.name}")
            try:
                df = parse_output.parse_indicator_csv(file_path)
                summary = parse_output.get_indicator_summary(df)
                print(f"     Indicators: {summary['total_indicators']}")
                if summary['buckets']:
                    top_bucket = max(summary['buckets'].items(), key=lambda x: x[1])
                    print(f"     Top Bucket: {top_bucket[0]} ({top_bucket[1]} indicators)")
                if summary['date_range']:
                    print(f"     Date Range: {summary['date_range']['start']} to {summary['date_range']['end']}")
            except Exception as e:
                print(f"     Error parsing: {e}")
    else:
        print("  No indicator files found")
    
    # Show most recent files details
    print("\n" + "=" * 60)
    print("Most Recent Files Details")
    print("=" * 60)
    
    if calendar_files:
        print("\n📅 Most Recent Calendar File:")
        try:
            df = parse_output.parse_calendar_csv()
            summary = parse_output.get_calendar_summary(df)
            print(f"  Total Entries: {summary['total_entries']}")
            if summary['date_range']:
                print(f"  Date Range: {summary['date_range']['start']} to {summary['date_range']['end']}")
            if summary['categories']:
                print(f"  Categories ({len(summary['categories'])}):")
                for cat, count in sorted(summary['categories'].items(), key=lambda x: x[1], reverse=True)[:10]:
                    print(f"    - {cat}: {count}")
            if summary['impact_distribution']:
                print(f"  Impact Distribution:")
                for impact, count in sorted(summary['impact_distribution'].items()):
                    print(f"    - Level {impact}: {count}")
        except Exception as e:
            print(f"  Error: {e}")
    
    if indicator_files:
        print("\n📊 Most Recent Indicator File:")
        try:
            df = parse_output.parse_indicator_csv()
            summary = parse_output.get_indicator_summary(df)
            print(f"  Total Indicators: {summary['total_indicators']}")
            if summary['buckets']:
                print(f"  Buckets ({len(summary['buckets'])}):")
                for bucket, count in sorted(summary['buckets'].items(), key=lambda x: x[1], reverse=True)[:10]:
                    print(f"    - {bucket}: {count}")
            if summary['date_range']:
                print(f"  Date Range: {summary['date_range']['start']} to {summary['date_range']['end']}")
        except Exception as e:
            print(f"  Error: {e}")


async def main_async(mode: str) -> None:
    if mode not in {"dom", "xhr", "indicators", "fomc", "speeches", "parse"}:
        raise SystemExit(f"Unsupported mode: {mode}")

    if mode == "dom":
        rows = await run_dom_mode()
        if not rows:
            raise SystemExit("No rows collected after filtering.")

        start_kst, end_kst = date_window_kst()
        output_path = save_csv.save_calendar_csv(rows, start_kst, end_kst)

        print(f"Saved {len(rows)} rows to {output_path}")
        impact_counter = Counter(row.get("impact") for row in rows if row.get("impact"))
        print("Impact distribution:", impact_counter)
        return

    if mode == "xhr":
        rows = await run_xhr_mode()
        if not rows:
            raise SystemExit("No rows collected after filtering.")

        start_kst, end_kst = date_window_kst()
        output_path = save_csv.save_calendar_csv(rows, start_kst, end_kst)

        print(f"Saved {len(rows)} rows to {output_path}")
        impact_counter = Counter(row.get("impact") for row in rows if row.get("impact"))
        print("Impact distribution:", impact_counter)
        return

    if mode == "indicators":
        indicator_rows: List[IndicatorRow] = indicators_dom.collect_indicators()
        if not indicator_rows:
            raise SystemExit("No indicators collected.")

        tz_kst = pytz.timezone(config.TZ_DISPLAY)
        today_kst = datetime.now(tz_kst).date()
        output_path = save_csv.save_indicators_csv(
            [asdict(row) for row in indicator_rows],
            today_kst,
        )

        print(f"Saved {len(indicator_rows)} indicator rows to {output_path}")
        bucket_counts = Counter(row.indicator_bucket for row in indicator_rows)
        print("Bucket distribution:", bucket_counts)
        return

    if mode == "fomc":
        await run_fomc_mode()
        return

    if mode == "speeches":
        await run_speeches_mode()
        return

    if mode == "parse":
        await run_parse_output_mode()
        return


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("dom", "xhr", "indicators", "fomc", "speeches", "parse"),
        default="dom",
        help="Scraper mode to run.",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)
    asyncio.run(main_async(args.mode))


if __name__ == "__main__":
    main()


