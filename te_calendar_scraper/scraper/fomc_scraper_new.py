"""FOMC meeting calendar scraper for Federal Reserve website.

This module scrapes FOMC meetings from 2020-2027 and downloads:
- FOMC Meeting Statement (HTML)
- Press Conference Transcript (PDF) - if available
- Minutes (HTML)
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

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


@dataclass
class MeetingMaterial:
    """Represents an FOMC meeting with all available materials."""
    year: int
    month: str
    dates: str  # e.g., "27-28" or "31-1"
    meeting_type: str = ""  # e.g., "FOMC Meeting", "Notation Vote"
    
    # URLs from calendar page
    press_conference_url: Optional[str] = None
    statement_url: Optional[str] = None
    minutes_url: Optional[str] = None
    other_materials_urls: list[str] = field(default_factory=list)
    
    # URLs discovered from press conference page (if followed)
    statement_html_url: Optional[str] = None
    press_conference_pdf_url: Optional[str] = None
    minutes_html_url: Optional[str] = None
    
    # Meeting-specific page URL (if press conference exists)
    meeting_page_url: Optional[str] = None
    
    # Release date parsed from meeting pages (used for filtering recent months)
    release_date: Optional[datetime] = None
    
    def get_final_minutes_html_url(self) -> Optional[str]:
        """Get the final minutes HTML URL, preferring press conference page over calendar page.
        
        Returns:
            The best available minutes HTML URL, or None if not available.
        """
        # Prefer minutes_html_url from press conference page if it exists and is HTML
        if self.minutes_html_url:
            return self.minutes_html_url
        
        # Fall back to minutes_url from calendar page if it's HTML
        if self.minutes_url and ".html" in self.minutes_url.lower():
            return self.minutes_url
        
        return None


def fetch_calendar_html() -> str:
    """Fetch the FOMC calendar HTML page.
    
    Returns:
        HTML content as string.
    """
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(FOMC_CALENDAR_URL, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def parse_meetings(calendar_html: str) -> list[MeetingMaterial]:
    """Parse the calendar HTML to extract meeting information.
    
    Uses DOM order of year headers (not numeric sorting) to correctly
    associate meeting elements with their year sections.
    
    Args:
        calendar_html: HTML content of the calendar page.
        
    Returns:
        List of MeetingMaterial objects with basic meeting info and URLs.
    """
    soup = BeautifulSoup(calendar_html, "html.parser")
    meetings: list[MeetingMaterial] = []
    
    month_pattern = re.compile(
        r"\b(January|February|March|April|May|June|July|August|"
        r"September|October|November|December|Jan/Feb|Apr/May|Oct/Nov)\b",
        re.I
    )
    
    # Find all year headers in DOM order - look for patterns like "2025 FOMC Meetings"
    # CRITICAL: We must preserve DOM order, not sort by year number
    year_headers = []  # List of (year, header_element) tuples in DOM order
    
    for elem in soup.find_all(["h2", "h3", "h4", "h5", "p", "div", "strong", "b"]):
        elem_text = elem.get_text().strip()
        if "FOMC" in elem_text.upper() and "MEETINGS" in elem_text.upper():
            year_match = re.search(r"\b(20\d{2})\s+FOMC\s+Meetings", elem_text, re.I)
            if year_match:
                found_year = int(year_match.group(1))
                if 2020 <= found_year <= 2027:
                    year_headers.append((found_year, elem))
                    logger.info(f"Found year header for {found_year} at DOM position {len(year_headers)}: {elem_text[:50]}")
    
    # Fallback: look for just year patterns in headers
    if len(year_headers) < 5:
        for elem in soup.find_all(["h2", "h3", "h4", "h5"]):
            elem_text = elem.get_text().strip()
            year_match = re.search(r"\b(20\d{2})\b", elem_text)
            if year_match:
                found_year = int(year_match.group(1))
                # Check if we already have this year
                if 2020 <= found_year <= 2027 and found_year not in [y for y, _ in year_headers]:
                    if len(elem_text) < 30 and "|" not in elem_text:
                        year_headers.append((found_year, elem))
                        logger.info(f"Found year header for {found_year} (alternative) at DOM position {len(year_headers)}: {elem_text[:50]}")
    
    logger.info(f"Found {len(year_headers)} year headers in DOM order: {[y for y, _ in year_headers]}")
    if len(year_headers) < 5:
        logger.warning(f"Expected to find year headers for 2020-2027, but only found {len(year_headers)} years")
    
    # Process each year in DOM order (not numeric order!)
    for i, (year, year_header) in enumerate(year_headers):
        # Find the next year header in DOM order
        next_year_header = year_headers[i + 1][1] if i + 1 < len(year_headers) else None
        
        # Collect all elements between this year header and the next one
        year_content = []
        
        # Use a simpler approach: find_all_next and filter by next_year_header
        if next_year_header:
            # Get all elements after this year header
            all_after = year_header.find_all_next(["p", "div", "li", "table", "tr", "td"])
            # Get all elements before next year header
            all_before_next = next_year_header.find_all_previous(["p", "div", "li", "table", "tr", "td"])
            # Intersection: elements that are both after current and before next
            year_content = [e for e in all_after if e in all_before_next]
        else:
            # No next year header, collect everything after this header
            year_content = year_header.find_all_next(["p", "div", "li", "table", "tr", "td"])
        
        # Also include children of year header itself
        for child in year_header.find_all(["p", "div", "li", "table", "tr", "td"], recursive=True):
            if child not in year_content:
                year_content.append(child)
        
        logger.info(f"Year {year}: collected {len(year_content)} content elements")
        if len(year_content) == 0:
            logger.warning(f"Year {year}: No content elements collected! This may indicate a parsing issue.")
        
        # Parse meetings in this year's content
        # Use a simpler approach: look for meeting blocks (table rows or groups of <p> elements)
        seen_meetings = set()
        date_pattern = re.compile(r"(\d{1,2}(?:-\d{1,2})?)")
        
        # Build a list of potential meeting blocks
        # A meeting block is typically a <tr> or a group of consecutive <p>/<div> elements
        meeting_blocks = []
        
        # First, collect table rows as potential meeting blocks
        for table in [c for c in year_content if hasattr(c, 'name') and c.name == 'table']:
            for row in table.find_all('tr'):
                meeting_blocks.append(row)
        
        # Also collect individual <p>, <div>, <li> elements
        for elem in year_content:
            if hasattr(elem, 'name') and elem.name in ['p', 'div', 'li'] and elem not in meeting_blocks:
                meeting_blocks.append(elem)
        
        for container in meeting_blocks:
            # Treat the container itself as a candidate
            candidate_elems = []
            if hasattr(container, "name") and container.name in ("p", "div", "li", "td", "tr"):
                candidate_elems.append(container)
            candidate_elems.extend(container.find_all(["p", "div", "li", "td"], recursive=True))
            
            for elem in candidate_elems:
                text = elem.get_text()
                text_lower = text.lower()
                
                # Skip "Released" lines
                if "released" in text_lower and any(m in text_lower for m in 
                    ["january", "february", "march", "april", "may", "june", 
                     "july", "august", "september", "october", "november", "december"]):
                    continue
                
                # Find month and date
                month_match = month_pattern.search(text)
                if not month_match:
                    continue
                
                month_raw = month_match.group(1)
                month_start = month_match.start()
                
                # Normalize month names
                if "/" in month_raw:
                    month_part = month_raw.split("/")[0].strip()
                    month_abbrev_to_full = {
                        'Jan': 'January', 'Feb': 'February', 'Mar': 'March', 'Apr': 'April',
                        'May': 'May', 'Jun': 'June', 'Jul': 'July', 'Aug': 'August',
                        'Sep': 'September', 'Oct': 'October', 'Nov': 'November', 'Dec': 'December'
                    }
                    month = month_abbrev_to_full.get(month_part, month_part.capitalize())
                else:
                    month = month_raw
                
                # Find date
                date_text = text[month_match.end():].lstrip()
                date_match = date_pattern.search(date_text)
                if not date_match:
                    # Try parent if it's a table row
                    if elem.parent and elem.parent.name == "tr":
                        parent_text = elem.parent.get_text()
                        date_match = date_pattern.search(parent_text)
                
                if not date_match:
                    continue
                
                dates = date_match.group(1)
                
                # Skip if this is a "Released" date
                if "released" in text[:month_start].lower():
                    continue
                
                # Create unique key
                meeting_key = (year, month, dates)
                if meeting_key in seen_meetings:
                    continue
                seen_meetings.add(meeting_key)
                
                # Determine meeting type
                meeting_type = "FOMC Meeting"
                if "notation vote" in text_lower:
                    meeting_type = "Notation Vote"
                
                # Collect links from the meeting block
                links = []
                
                # If container is a table row, collect all links from that row
                if container.name == "tr":
                    links = container.find_all("a", href=True)
                else:
                    # For non-table structures, collect links from elem and nearby siblings
                    links = list(elem.find_all("a", href=True))
                    
                    # Check parent if it's a reasonable container
                    if elem.parent and elem.parent.name in ["div", "li", "td"]:
                        parent_text = elem.parent.get_text().lower()
                        if month.lower() in parent_text and dates in parent_text:
                            for link in elem.parent.find_all("a", href=True):
                                if link not in links:
                                    links.append(link)
                    
                    # Check immediate siblings (next few elements)
                    current = elem.next_sibling
                    sibling_count = 0
                    while current and sibling_count < 5:
                        if hasattr(current, 'find_all'):
                            current_text = current.get_text().lower()
                            has_meeting_keywords = any(kw in current_text for kw in 
                                ["statement", "minutes", "press conference", "transcript"])
                            has_our_date = month.lower() in current_text and dates in current_text
                            
                            if has_meeting_keywords or has_our_date:
                                for link in current.find_all("a", href=True):
                                    if link not in links:
                                        links.append(link)
                        
                        current = current.next_sibling if hasattr(current, 'next_sibling') else None
                        sibling_count += 1
                
                # Filter links to only those relevant to this meeting
                validated_links = []
                for link in links:
                    link_text = link.get_text().strip().lower()
                    href = link.get("href", "").lower()
                    
                    # Check if link is in a context with our month/date
                    link_container = link.find_parent(["p", "div", "li", "td", "tr"])
                    if link_container:
                        container_text = link_container.get_text().lower()
                        has_our_date = month.lower() in container_text and dates in container_text
                        is_meeting_link = any(kw in link_text or kw in href for kw in 
                            ["statement", "minutes", "press conference", "transcript"])
                        
                        if has_our_date or is_meeting_link:
                            validated_links.append(link)
                    else:
                        # No parent, include if it's a meeting link
                        is_meeting_link = any(kw in link_text or kw in href for kw in 
                            ["statement", "minutes", "press conference", "transcript"])
                        if is_meeting_link:
                            validated_links.append(link)
                
                links = validated_links
                
                # If no links found, skip this potential meeting
                if not links:
                    logger.debug(f"Skipping {year} {month} {dates} - no meeting links found")
                    continue
                
                # Extract URLs from validated links
                press_conference_url = None
                statement_url = None
                minutes_url = None
                other_materials = []
                
                for link in links:
                    href = link.get("href", "")
                    if not href:
                        continue
                    
                    link_text = link.get_text().strip().lower()
                    href_lower = href.lower()
                    full_url = urljoin(FOMC_BASE_URL, href)
                    
                    # Check for Press Conference link
                    if ("press conference" in link_text or "pressconference" in link_text or
                        "press conference" in href_lower):
                        if not press_conference_url:
                            press_conference_url = full_url
                    
                    # Check for Statement link
                    elif "statement" in link_text:
                        # Check if it's a special statement
                        is_special = any(kw in link_text for kw in 
                            ["longer-run goals", "monetary policy strategy", "notation vote",
                             "plans for reducing", "balance sheet"])
                        
                        if is_special:
                            if full_url not in other_materials:
                                other_materials.append(full_url)
                        else:
                            if ".html" in href_lower or (".pdf" not in href_lower and not statement_url):
                                statement_url = full_url
                            elif ".pdf" in href_lower and not statement_url:
                                if full_url not in other_materials:
                                    other_materials.append(full_url)
                    
                    # Check for Minutes link
                    elif "minutes" in link_text:
                        if ".html" in href_lower or (".pdf" not in href_lower and not minutes_url):
                            minutes_url = full_url
                    
                    # Check for HTML/PDF links in context
                    elif link_text in ["html", "pdf"] or link_text == "":
                        link_parent = link.find_parent(["p", "div", "li", "td"])
                        if link_parent:
                            parent_text = link_parent.get_text().lower()
                            if "statement:" in parent_text and not statement_url:
                                is_special = any(kw in parent_text for kw in ["longer-run", "notation vote"])
                                if not is_special:
                                    if ".html" in href_lower or (link_text == "html" and ".pdf" not in href_lower):
                                        statement_url = full_url
                            elif "minutes:" in parent_text and not minutes_url:
                                if ".html" in href_lower or (link_text == "html" and ".pdf" not in href_lower):
                                    minutes_url = full_url
                    
                    # Other materials
                    else:
                        link_parent = link.find_parent(["p", "div", "li", "td"])
                        if link_parent:
                            parent_text = link_parent.get_text().lower()
                            if (month.lower() in parent_text and dates in parent_text and
                                full_url not in other_materials and
                                full_url != press_conference_url and
                                full_url != statement_url and
                                full_url != minutes_url):
                                other_materials.append(full_url)
                
                # Create meeting material
                meeting = MeetingMaterial(
                    year=year,
                    month=month,
                    dates=dates,
                    meeting_type=meeting_type,
                    press_conference_url=press_conference_url,
                    statement_url=statement_url,
                    minutes_url=minutes_url,
                    other_materials_urls=other_materials,
                )
                meetings.append(meeting)
                logger.debug(f"Created meeting: {year} {month} {dates} with {len(links)} links")
        
        year_meetings = [m for m in meetings if m.year == year]
        logger.info(f"Year {year}: found {len(year_meetings)} meetings")
        if len(year_meetings) == 0 and len(year_content) > 0:
            logger.warning(f"Year {year}: Found {len(year_content)} content elements but no meetings. Month/date parsing may be failing.")
    
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
    
    # Fallback: try generic "Month Day, Year" pattern
    generic_pattern = re.compile(
        r"(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+"
        r"(\d{1,2}),\s+"
        r"(\d{4})",
        re.I
    )
    
    match = generic_pattern.search(text)
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


def enrich_meeting_from_press_conf(material: MeetingMaterial) -> MeetingMaterial:
    """Follow the press conference link and extract Statement, Transcript, and Minutes URLs.
    
    Args:
        material: MeetingMaterial with press_conference_url set.
        
    Returns:
        Updated MeetingMaterial with statement_html_url, press_conference_pdf_url, 
        and minutes_html_url populated.
    """
    if not material.press_conference_url:
        return material
    
    headers = {"User-Agent": USER_AGENT}
    
    try:
        response = requests.get(material.press_conference_url, headers=headers, timeout=30)
        response.raise_for_status()
        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        
        # Store the meeting page URL
        material.meeting_page_url = material.press_conference_url
        
        # Find all links on the page
        all_links = soup.find_all("a", href=True)
        
        for link in all_links:
            href = link.get("href", "")
            if not href:
                continue
            
            link_text = link.get_text().strip().lower()
            href_lower = href.lower()
            full_url = urljoin(FOMC_BASE_URL, href)
            
            # Get context from parent elements
            link_context = link.find_parent(["p", "div", "li", "td", "span"])
            context_text = link_context.get_text().lower() if link_context else ""
            
            # Find FOMC Meeting Statement (HTML)
            if not material.statement_html_url:
                if "statement" in link_text:
                    is_special = any(kw in link_text or kw in context_text 
                                    for kw in ["longer-run", "notation vote", "balance sheet"])
                    if not is_special:
                        if ".html" in href_lower and ".pdf" not in href_lower:
                            if ("fomc" in context_text or "meeting" in context_text or 
                                "statement" in context_text or not context_text):
                                material.statement_html_url = full_url
                        elif ".pdf" not in href_lower and "html" in context_text:
                            if "fomc" in context_text or "meeting" in context_text or "statement" in context_text:
                                material.statement_html_url = full_url
                elif link_text == "html":
                    statement_contexts = ["statement:", "statement", "meeting statement", "fomc statement"]
                    if any(ctx in context_text for ctx in statement_contexts):
                        is_special = any(kw in context_text for kw in ["longer-run", "notation vote"])
                        if not is_special:
                            if ".html" in href_lower or ".pdf" not in href_lower:
                                material.statement_html_url = full_url
            
            # Find Press Conference Transcript (PDF)
            if not material.press_conference_pdf_url:
                if (("press conference" in link_text or "transcript" in link_text or 
                     "press conference" in context_text) and ".pdf" in href_lower):
                    material.press_conference_pdf_url = full_url
                elif "transcript" in link_text and ".pdf" in href_lower:
                    material.press_conference_pdf_url = full_url
            
            # Find Minutes (HTML)
            if not material.minutes_html_url:
                if "minutes" in link_text:
                    if ".html" in href_lower and ".pdf" not in href_lower:
                        material.minutes_html_url = full_url
                    elif ".pdf" not in href_lower and "html" in context_text:
                        material.minutes_html_url = full_url
                elif link_text == "html":
                    minutes_contexts = [
                        "minutes:",
                        "minutes",
                        "minutes of the federal open market committee",
                        "fomc minutes",
                    ]
                    if any(ctx in context_text for ctx in minutes_contexts):
                        if ".html" in href_lower or ".pdf" not in href_lower:
                            material.minutes_html_url = full_url
        
        # Also search for common patterns where links are just labeled "HTML" or "PDF"
        for section in soup.find_all(["p", "div", "li"]):
            section_text = section.get_text().lower()
            
            # Check for Statement section
            if not material.statement_html_url:
                statement_phrases = [
                    "statement:",
                    "statement",
                    "meeting statement",
                    "fomc meeting statement",
                    "fomc statement",
                ]
                has_statement_context = any(phrase in section_text for phrase in statement_phrases)
                is_special = any(kw in section_text for kw in ["longer-run", "notation vote", "balance sheet"])
                
                if has_statement_context and not is_special:
                    html_links = section.find_all("a", href=True)
                    for link in html_links:
                        href = link.get("href", "")
                        if not href:
                            continue
                        href_lower = href.lower()
                        full_url = urljoin(FOMC_BASE_URL, href)
                        link_text = link.get_text().strip().lower()
                        
                        if (link_text == "html" or ".html" in href_lower) and ".pdf" not in href_lower:
                            material.statement_html_url = full_url
                            break
            
            # Check for Minutes section
            if not material.minutes_html_url:
                minutes_phrases = [
                    "minutes:",
                    "minutes",
                    "minutes of the federal open market committee",
                    "fomc minutes",
                ]
                has_minutes_context = any(phrase in section_text for phrase in minutes_phrases)
                
                if has_minutes_context:
                    html_links = section.find_all("a", href=True)
                    for link in html_links:
                        href = link.get("href", "")
                        if not href:
                            continue
                        href_lower = href.lower()
                        full_url = urljoin(FOMC_BASE_URL, href)
                        link_text = link.get_text().strip().lower()
                        
                        if (link_text == "html" or ".html" in href_lower) and ".pdf" not in href_lower:
                            material.minutes_html_url = full_url
                            break
        
        # Parse release dates from the page
        page_text = soup.get_text()
        
        # Try to find release date in statement section
        if not material.release_date:
            for section in soup.find_all(["p", "div", "li"]):
                section_text = section.get_text()
                if any(phrase in section_text.lower() for phrase in 
                       ["statement:", "statement", "meeting statement", "fomc meeting statement"]):
                    release_date = parse_release_date(section_text)
                    if release_date:
                        material.release_date = release_date
                        break
        
        # Try to find release date in minutes section if not found yet
        if not material.release_date:
            for section in soup.find_all(["p", "div", "li"]):
                section_text = section.get_text()
                if any(phrase in section_text.lower() for phrase in 
                       ["minutes:", "minutes", "fomc minutes"]):
                    release_date = parse_release_date(section_text)
                    if release_date:
                        material.release_date = release_date
                        break
        
        # Fallback: search entire page for release date
        if not material.release_date:
            material.release_date = parse_release_date(page_text)
        
        logger.debug(f"Enriched meeting {material.year} {material.month} {material.dates}: "
                     f"release_date={material.release_date}, "
                     f"statement_html={bool(material.statement_html_url)}, "
                     f"minutes_html={bool(material.minutes_html_url)}, "
                     f"transcript_pdf={bool(material.press_conference_pdf_url)}")
        
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch press conference page for {material.year} {material.month} {material.dates}: {e}")
    
    return material


def enrich_meeting_from_fallback(material: MeetingMaterial) -> MeetingMaterial:
    """Follow a fallback link (for meetings without press conference) and extract materials.
    
    For meetings without press conference links, this function follows any available
    link (usually a press release) and extracts PDF URLs and release dates.
    
    Args:
        material: MeetingMaterial with at least one URL in other_materials_urls or statement_url.
        
    Returns:
        Updated MeetingMaterial with PDF URLs and release_date populated.
    """
    # Find a URL to follow - prefer statement_url, then other_materials_urls
    url_to_follow = None
    if material.statement_url:
        url_to_follow = material.statement_url
    elif material.other_materials_urls:
        url_to_follow = material.other_materials_urls[0]
    elif material.minutes_url:
        url_to_follow = material.minutes_url
    
    if not url_to_follow:
        logger.debug(f"No fallback URL found for {material.year} {material.month} {material.dates}")
        return material
    
    headers = {"User-Agent": USER_AGENT}
    
    try:
        response = requests.get(url_to_follow, headers=headers, timeout=30)
        response.raise_for_status()
        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        
        # Store the meeting page URL
        material.meeting_page_url = url_to_follow
        
        # Find all PDF links on the page
        pdf_urls = []
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            href_lower = href.lower()
            if ".pdf" in href_lower:
                full_url = urljoin(FOMC_BASE_URL, href)
                if full_url not in pdf_urls:
                    pdf_urls.append(full_url)
        
        # Store PDFs in other_materials_urls if not already there
        for pdf_url in pdf_urls:
            if pdf_url not in material.other_materials_urls:
                material.other_materials_urls.append(pdf_url)
        
        # Parse release date from page
        page_text = soup.get_text()
        material.release_date = parse_release_date(page_text)
        
        # If no release date found, try to extract from page title or heading
        if not material.release_date:
            for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5"]):
                heading_text = heading.get_text()
                release_date = parse_release_date(heading_text)
                if release_date:
                    material.release_date = release_date
                    break
        
        logger.debug(f"Enriched fallback meeting {material.year} {material.month} {material.dates}: "
                     f"release_date={material.release_date}, "
                     f"found {len(pdf_urls)} PDF(s)")
        
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch fallback page for {material.year} {material.month} {material.dates}: {e}")
    
    return material


def download_material(url: str, output_dir: Path, filename: str) -> Optional[Path]:
    """Download a material (HTML or PDF) from a URL.
    
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


def filter_recent_10_months(meetings: list[MeetingMaterial]) -> list[MeetingMaterial]:
    """Filter meetings to the most recent 10 distinct (year, month) pairs.
    
    Meetings are sorted by release_date descending, and we keep meetings
    whose (year, month) is in the 10 most recent months.
    
    Args:
        meetings: List of all MeetingMaterial objects.
        
    Returns:
        Filtered list containing only meetings from the most recent 10 months.
    """
    # Filter out meetings without release_date
    meetings_with_date = [m for m in meetings if m.release_date is not None]
    meetings_without_date = [m for m in meetings if m.release_date is None]
    
    if not meetings_with_date:
        logger.warning("No meetings with release_date found. Returning all meetings.")
        return meetings
    
    # Sort by release_date descending
    meetings_with_date.sort(key=lambda m: m.release_date, reverse=True)
    
    # First pass: identify the 10 most recent distinct months
    seen_months = set()
    for meeting in meetings_with_date:
        if meeting.release_date:
            month_key = (meeting.release_date.year, meeting.release_date.month)
            if month_key not in seen_months:
                if len(seen_months) < 10:
                    seen_months.add(month_key)
                else:
                    # We've identified 10 distinct months, stop
                    break
    
    # Second pass: collect all meetings from those 10 months
    recent_meetings = []
    for meeting in meetings_with_date:
        if meeting.release_date:
            month_key = (meeting.release_date.year, meeting.release_date.month)
            if month_key in seen_months:
                recent_meetings.append(meeting)
    
    logger.info(f"Filtered to {len(recent_meetings)} meetings from {len(seen_months)} distinct months")
    logger.info(f"Months included: {sorted(seen_months, reverse=True)}")
    
    if meetings_without_date:
        logger.warning(f"{len(meetings_without_date)} meetings without release_date were excluded from filtering")
    
    return recent_meetings


def scrape_fomc_calendar() -> list[MeetingMaterial]:
    """Main function to scrape FOMC calendar and enrich meetings.
    
    Returns:
        List of MeetingMaterial objects filtered to the most recent 10 months,
        with all available URLs and release dates populated.
    """
    logger.info("Fetching FOMC calendar page...")
    calendar_html = fetch_calendar_html()
    
    logger.info("Parsing meetings from calendar...")
    meetings = parse_meetings(calendar_html)
    
    # Log meetings by year for debugging
    by_year = defaultdict(list)
    for m in meetings:
        by_year[m.year].append(m)
    
    logger.info(f"Found {len(meetings)} total meetings")
    if len(meetings) == 0:
        logger.warning("No meetings found! This may indicate a parsing issue.")
    for year in sorted(by_year.keys()):
        logger.info(f"  {year}: {len(by_year[year])} meetings")
    if len(by_year) > 0:
        latest_year = max(by_year.keys())
        logger.info(f"Latest year found: {latest_year}")
        if latest_year < 2024:
            logger.warning(f"Only found meetings up to {latest_year}. Expected to find meetings through 2025-2027.")
    
    # Enrich meetings that have press conference links
    logger.info("Enriching meetings with press conference data...")
    press_conf_count = 0
    for meeting in meetings:
        if meeting.press_conference_url:
            enrich_meeting_from_press_conf(meeting)
            press_conf_count += 1
    
    logger.info(f"Successfully enriched {press_conf_count} meetings with press conference data")
    
    # Enrich meetings without press conference links (fallback)
    logger.info("Enriching meetings without press conference links (fallback)...")
    fallback_count = 0
    for meeting in meetings:
        if not meeting.press_conference_url:
            enrich_meeting_from_fallback(meeting)
            fallback_count += 1
    
    logger.info(f"Successfully enriched {fallback_count} meetings with fallback data")
    
    # Filter to most recent 10 months
    logger.info("Filtering to most recent 10 months based on release_date...")
    filtered_meetings = filter_recent_10_months(meetings)
    
    # Log details for each meeting in the final set
    logger.info("=" * 80)
    logger.info(f"Final set: {len(filtered_meetings)} meetings from recent 10 months")
    logger.info("=" * 80)
    for meeting in sorted(filtered_meetings, key=lambda m: m.release_date or datetime.min, reverse=True):
        source = "Press Conference page" if meeting.press_conference_url else "Fallback page"
        logger.info(f"Meeting: {meeting.year} {meeting.month} {meeting.dates} ({meeting.meeting_type})")
        logger.info(f"  Release date: {meeting.release_date}")
        logger.info(f"  Source: {source}")
        logger.info(f"  Statement HTML URL: {meeting.statement_html_url or meeting.statement_url or 'None'}")
        logger.info(f"  Minutes HTML URL: {meeting.minutes_html_url or meeting.minutes_url or 'None'}")
        logger.info(f"  Press Conference Transcript PDF: {meeting.press_conference_pdf_url or 'None'}")
        if meeting.other_materials_urls:
            logger.info(f"  Other materials: {len(meeting.other_materials_urls)} URL(s)")
        logger.info("")
    
    return filtered_meetings

