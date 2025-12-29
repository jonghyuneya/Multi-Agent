"""FOMC press conference transcript scraper for Federal Reserve website.

SIMPLIFIED VERSION - Only collects recent press conference transcripts (PDF).

This module scrapes the FOMC calendar to find recent press conference transcript PDFs.
It does NOT download statements or minutes - only the press conference PDF files.

Strategy:
1. Parse FOMC calendar page to find meetings with "Press Conference" links
2. Follow each link to the meeting page
3. Extract the press conference transcript PDF URL and release date
4. Filter to most recent N transcripts (default: 10)
5. Return deduplicated list of transcripts
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from te_calendar_scraper import config

logger = logging.getLogger(__name__)

# Base URL for Federal Reserve
FOMC_BASE_URL = "https://www.federalreserve.gov"
FOMC_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

# User agent to mimic a browser
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

# Number of recent transcripts to keep
NUM_RECENT_TRANSCRIPTS = 10


@dataclass
class TranscriptMaterial:
    """Represents an FOMC press conference transcript."""
    year: int
    month: str
    dates: str  # e.g., "28-29" or "31-1"
    
    # Press conference transcript PDF URL
    press_conference_pdf_url: Optional[str] = None
    
    # Meeting page URL (press conference page)
    meeting_page_url: Optional[str] = None
    
    # Release date parsed from meeting page
    release_date: Optional[datetime] = None


def fetch_calendar_html() -> str:
    """Fetch the FOMC calendar HTML page.
    
    Returns:
        HTML content as string.
    """
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(FOMC_CALENDAR_URL, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def parse_calendar_for_meetings(calendar_html: str) -> list[TranscriptMaterial]:
    """Parse calendar HTML to find meetings with press conference links.
    
    This is a simplified parser that focuses on finding:
    - Meeting date (year, month, dates)
    - Press Conference link (to meeting page)
    
    Args:
        calendar_html: HTML content of the calendar page.
        
    Returns:
        List of TranscriptMaterial objects with basic info and meeting_page_url.
    """
    soup = BeautifulSoup(calendar_html, "html.parser")
    meetings: list[TranscriptMaterial] = []
    
    # Strategy: Find all table rows or list items that contain meeting information
    # Look for patterns like "January 28-29" followed by a "Press Conference" link
    
    # Month pattern
    month_pattern = re.compile(
        r"\b(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\b",
        re.I
    )
    
    # Find all potential meeting containers (table rows, list items, divs)
    containers = soup.find_all(["tr", "li", "div", "p"])
    
    # Track seen meetings to avoid duplicates
    seen_meetings: set[tuple[int, str, str]] = set()
    
    # Try to infer year from context (look for year headers)
    current_year = None
    year_pattern = re.compile(r"\b(202[0-7])\s+FOMC\s+Meetings", re.I)
    
    for container in containers:
        text = container.get_text()
        
        # Check if this is a year header
        year_match = year_pattern.search(text)
        if year_match:
            current_year = int(year_match.group(1))
            continue
        
        # Look for month and date pattern
        month_match = month_pattern.search(text)
        if not month_match:
            continue
        
        month = month_match.group(1)
        
        # Look for date pattern (e.g., "28-29" or "22")
        date_pattern = re.compile(r"\b(\d{1,2}(?:-\d{1,2})?)\b")
        date_match = date_pattern.search(text, month_match.end())
        if not date_match:
            continue
        
        dates = date_match.group(1)
        
        # If we don't have a year yet, try to extract from nearby headers
        if current_year is None:
            # Look backwards for year header
            prev = container.find_previous(["h2", "h3", "h4", "h5"])
            if prev:
                prev_year_match = re.search(r"\b(202[0-7])\b", prev.get_text())
                if prev_year_match:
                    current_year = int(prev_year_match.group(1))
        
        if current_year is None:
            continue  # Skip if we can't determine year
        
        # Check for duplicate
        meeting_key = (current_year, month, dates)
        if meeting_key in seen_meetings:
            continue
        
        # Look for "Press Conference" link in this container
        press_conf_link = None
        for link in container.find_all("a", href=True):
            link_text = link.get_text().strip().lower()
            if "press conference" in link_text or "pressconference" in link_text:
                press_conf_link = urljoin(FOMC_BASE_URL, link.get("href"))
                break
        
        # Fallback: if no press conference link, take any link in this container
        if not press_conf_link:
            links = container.find_all("a", href=True)
            if links:
                # Prefer links that look like meeting pages (not external or calendar links)
                for link in links:
                    href = link.get("href", "")
                    if "monetarypolicy" in href and "calendar" not in href:
                        press_conf_link = urljoin(FOMC_BASE_URL, href)
                        break
                
                # If still no link, take the first one
                if not press_conf_link and links:
                    press_conf_link = urljoin(FOMC_BASE_URL, links[0].get("href"))
        
        # Only create meeting if we have a link to follow
        if press_conf_link:
            seen_meetings.add(meeting_key)
            meeting = TranscriptMaterial(
                year=current_year,
                month=month,
                dates=dates,
                meeting_page_url=press_conf_link,
            )
            meetings.append(meeting)
            logger.debug(f"Found meeting: {current_year} {month} {dates} -> {press_conf_link}")
    
    return meetings


def parse_release_date(text: str) -> Optional[datetime]:
    """Parse a release date from text containing 'Released ...' pattern.
    
    Args:
        text: Text that may contain a release date.
        
    Returns:
        Parsed datetime if found, None otherwise.
    """
    # Pattern: "Released January 29, 2025 at 2:00 p.m."
    released_pattern = re.compile(
        r"Released\s+"
        r"(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+"
        r"(\d{1,2}),\s+"
        r"(\d{4})",
        re.I
    )
    
    match = released_pattern.search(text)
    if match:
        month_name = match.group(1)
        day = int(match.group(2))
        year = int(match.group(3))
        
        month_map = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12
        }
        month = month_map.get(month_name.lower())
        if month:
            try:
                return datetime(year, month, day)
            except ValueError:
                pass
    
    return None


def extract_transcript_from_meeting_page(material: TranscriptMaterial) -> TranscriptMaterial:
    """Follow meeting page link and extract press conference transcript PDF URL.
    
    Strategy:
    1. Look for explicit "Press Conference Transcript (PDF)" link
    2. Fallback: any PDF link on the page
    3. Extract release date from "Released ..." text
    
    Args:
        material: TranscriptMaterial with meeting_page_url set.
        
    Returns:
        Updated TranscriptMaterial with press_conference_pdf_url and release_date.
    """
    if not material.meeting_page_url:
        return material
    
    headers = {"User-Agent": USER_AGENT}
    
    try:
        response = requests.get(material.meeting_page_url, headers=headers, timeout=30)
        response.raise_for_status()
        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        
        # Find all links on the page
        all_links = soup.find_all("a", href=True)
        
        # Strategy 1: Look for explicit press conference transcript link
        for link in all_links:
            href = link.get("href", "")
            link_text = link.get_text().strip().lower()
            href_lower = href.lower()
            
            # Check if this is a press conference transcript PDF
            if ".pdf" in href_lower:
                # Check link text and context
                if "press conference" in link_text or "transcript" in link_text:
                    material.press_conference_pdf_url = urljoin(FOMC_BASE_URL, href)
                    break
                
                # Check parent context
                parent = link.find_parent(["p", "div", "li"])
                if parent:
                    parent_text = parent.get_text().lower()
                    if "press conference" in parent_text and "transcript" in parent_text:
                        material.press_conference_pdf_url = urljoin(FOMC_BASE_URL, href)
                        break
        
        # Strategy 2: Fallback - take any PDF link on the page
        if not material.press_conference_pdf_url:
            for link in all_links:
                href = link.get("href", "")
                if ".pdf" in href.lower():
                    material.press_conference_pdf_url = urljoin(FOMC_BASE_URL, href)
                    logger.debug(f"Using fallback PDF for {material.year} {material.month} {material.dates}")
                    break
        
        # Extract release date from page
        page_text = soup.get_text()
        material.release_date = parse_release_date(page_text)
        
        # If no release date found in general text, look in specific sections
        if not material.release_date:
            for section in soup.find_all(["p", "div", "li"]):
                section_text = section.get_text()
                if "released" in section_text.lower():
                    release_date = parse_release_date(section_text)
                    if release_date:
                        material.release_date = release_date
                        break
        
        logger.debug(f"Extracted transcript for {material.year} {material.month} {material.dates}: "
                     f"pdf={bool(material.press_conference_pdf_url)}, "
                     f"release_date={material.release_date}")
        
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch meeting page for {material.year} {material.month} {material.dates}: {e}")
    
    return material


def download_material(url: str, output_dir: Path, filename: str) -> Optional[Path]:
    """Download a material (PDF) from a URL.
    
    Args:
        url: URL to download from.
        output_dir: Directory to save the file.
        filename: Filename to save as.
        
    Returns:
        Path to downloaded file, or None if download failed.
    """
    if not url:
        return None
    
    output_path = output_dir / filename
    
    # Skip if already exists
    if output_path.exists():
        logger.debug(f"File already exists: {output_path}")
        return output_path
    
    headers = {"User-Agent": USER_AGENT}
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Write file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(response.content)
        
        logger.info(f"Downloaded: {filename}")
        return output_path
        
    except requests.RequestException as e:
        logger.error(f"Failed to download {url}: {e}")
        return None


def scrape_fomc_calendar() -> list[TranscriptMaterial]:
    """Scrape recent FOMC press conference transcripts.
    
    This function:
    1. Parses the FOMC calendar to find meetings with press conference links
    2. Follows each link to extract the transcript PDF URL and release date
    3. Filters to the most recent NUM_RECENT_TRANSCRIPTS transcripts
    4. Returns deduplicated list of transcripts
    
    Returns:
        List of TranscriptMaterial objects with PDF URLs and release dates,
        filtered to the most recent transcripts.
    """
    logger.info("Fetching FOMC calendar page...")
    calendar_html = fetch_calendar_html()
    
    logger.info("Parsing calendar for meetings with press conference links...")
    meetings = parse_calendar_for_meetings(calendar_html)
    
    logger.info(f"Found {len(meetings)} meetings with press conference links")
    
    # Extract transcript PDFs from each meeting page
    logger.info("Extracting transcript PDFs from meeting pages...")
    for meeting in meetings:
        extract_transcript_from_meeting_page(meeting)
    
    # Filter to meetings that have a transcript PDF
    meetings_with_pdf = [m for m in meetings if m.press_conference_pdf_url]
    logger.info(f"Found {len(meetings_with_pdf)} meetings with transcript PDFs")
    
    # Filter to meetings with release dates (needed for sorting)
    meetings_with_date = [m for m in meetings_with_pdf if m.release_date]
    logger.info(f"Found {len(meetings_with_date)} meetings with release dates")
    
    # Sort by release date descending (most recent first)
    meetings_with_date.sort(key=lambda m: m.release_date, reverse=True)
    
    # Keep only the most recent N transcripts
    recent_transcripts = meetings_with_date[:NUM_RECENT_TRANSCRIPTS]
    
    logger.info("=" * 80)
    logger.info(f"Selected {len(recent_transcripts)} most recent transcripts:")
    logger.info("=" * 80)
    for transcript in recent_transcripts:
        logger.info(f"  {transcript.year} {transcript.month} {transcript.dates}")
        logger.info(f"    Release date: {transcript.release_date}")
        logger.info(f"    PDF URL: {transcript.press_conference_pdf_url}")
        logger.info("")
    
    return recent_transcripts


def download_recent_transcripts(transcripts: list[TranscriptMaterial]) -> dict[str, int]:
    """Download transcript PDFs to disk.
    
    Args:
        transcripts: List of TranscriptMaterial objects to download.
        
    Returns:
        Dictionary with counts: {'downloaded': N, 'skipped': M, 'failed': K}
    """
    downloaded = 0
    skipped = 0
    failed = 0
    
    for transcript in transcripts:
        if not transcript.press_conference_pdf_url:
            continue
        
        # Generate filename from meeting metadata
        # Format: YYYY_mmm_DD-DD_press_conference.pdf
        month_abbrev = {
            'January': 'jan', 'February': 'feb', 'March': 'mar', 'April': 'apr',
            'May': 'may', 'June': 'jun', 'July': 'jul', 'August': 'aug',
            'September': 'sep', 'October': 'oct', 'November': 'nov', 'December': 'dec',
        }
        month_abbr = month_abbrev.get(transcript.month, transcript.month[:3].lower())
        filename = f"{transcript.year}_{month_abbr}_{transcript.dates}_press_conference.pdf"
        
        # Check if file already exists
        existing_file = config.FOMC_DOWNLOADS_DIR / filename
        if existing_file.exists():
            skipped += 1
            logger.info(f"Skipped (exists): {transcript.year} {transcript.month} {transcript.dates}")
            continue
        
        # Download
        result = download_material(
            transcript.press_conference_pdf_url,
            config.FOMC_DOWNLOADS_DIR,
            filename,
        )
        
        if result and result.exists() and result.stat().st_size > 0:
            downloaded += 1
            logger.info(f"Downloaded: {transcript.year} {transcript.month} {transcript.dates}")
        else:
            failed += 1
            logger.error(f"Failed: {transcript.year} {transcript.month} {transcript.dates}")
    
    return {
        'downloaded': downloaded,
        'skipped': skipped,
        'failed': failed,
    }
