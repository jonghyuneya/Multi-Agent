"""Federal Reserve speeches scraper."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urljoin

from playwright.async_api import Page

from te_calendar_scraper import config


@dataclass
class Speech:
    """Represents a Federal Reserve speech with transcript link."""
    title: str
    speaker: str
    date: Optional[str] = None
    transcript_url: Optional[str] = None
    source_url: Optional[str] = None


async def scrape_speeches(page: Page) -> List[Speech]:
    """Scrape Federal Reserve speeches page and extract transcript links."""
    await page.goto(config.FED_SPEECHES_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)  # Wait for page to fully load
    
    speeches: List[Speech] = []
    
    # Wait for the speeches list to load
    try:
        await page.wait_for_selector("article, .speech-item, .event-item, li, .event", timeout=10000)
    except:
        pass
    
    # Parse the HTML content
    html_content = await page.content()
    speeches = _parse_speeches_html(html_content)
    
    return speeches


def _parse_speeches_html(html: str) -> List[Speech]:
    """Parse speeches HTML to extract speech information and transcript links."""
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, 'html.parser')
    speeches: List[Speech] = []
    
    # Find all links on the page that contain "transcript" in text or URL
    all_links = soup.find_all('a', href=True)
    
    seen_urls = set()  # Avoid duplicates
    
    for link in all_links:
        link_text = link.get_text(strip=True).lower()
        href = link.get('href', '').lower()
        
        # Look for transcript links - these are HTML pages, not PDFs
        # The link text might say "Transcript" or the URL might contain "transcript"
        is_transcript = (
            'transcript' in link_text or 
            'transcript' in href or
            (link_text == 'html' and 'transcript' in str(link.parent).lower())
        )
        
        if not is_transcript:
            continue
        
        # Skip PDF links - we only want HTML transcript pages
        if '.pdf' in href:
            continue
        
        # Get the full URL
        full_url = urljoin(config.FED_BASE_URL, link.get('href', ''))
        
        # Skip if we've already seen this URL
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        
        # Find the parent container to extract speech metadata
        # Look for common containers: article, li, div with classes
        parent = link.find_parent(['article', 'li', 'div', 'p', 'td'])
        
        title = ""
        speaker = ""
        date_text = ""
        
        if parent:
            # Try to find title - usually in h2, h3, h4, or strong tags
            title_elem = parent.find(['h2', 'h3', 'h4', 'h5', 'strong', 'b'])
            if title_elem:
                title = title_elem.get_text(strip=True)
            else:
                # Try finding a link with the speech title (usually the main link)
                title_link = parent.find('a', href=True)
                if title_link and title_link != link:
                    title = title_link.get_text(strip=True)
            
            # If still no title, try getting text from parent
            if not title:
                # Get all text and take the first meaningful line
                parent_text = parent.get_text(separator='\n', strip=True)
                lines = [line.strip() for line in parent_text.split('\n') if line.strip()]
                if lines:
                    # Skip common prefixes and find the actual title
                    for line in lines:
                        if line and len(line) > 10 and not line.lower().startswith(('by ', 'date:', 'transcript')):
                            title = line
                            break
            
            # Find speaker - look for patterns like "By [Name]" or speaker classes
            speaker_elem = parent.find(class_=re.compile(r'speaker|author|by', re.I))
            if not speaker_elem:
                # Look for text starting with "By"
                speaker_text = parent.find(string=re.compile(r'^by\s+', re.I))
                if speaker_text:
                    speaker_elem = speaker_text.find_parent(['span', 'p', 'div'])
            
            if speaker_elem:
                speaker = speaker_elem.get_text(strip=True)
                # Clean up "By " prefix if present
                speaker = re.sub(r'^by\s+', '', speaker, flags=re.I).strip()
            
            # Find date - look for date classes or date patterns
            date_elem = parent.find(class_=re.compile(r'date|time|published', re.I))
            if not date_elem:
                # Look for date patterns in text
                date_match = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\w+\s+\d{1,2},?\s+\d{4})\b', parent.get_text())
                if date_match:
                    date_text = date_match.group(1)
            else:
                date_text = date_elem.get_text(strip=True)
        
        # If we still don't have a title, use the link text or URL
        if not title:
            title = link.get_text(strip=True) or "Untitled Speech"
        
        speech = Speech(
            title=title,
            speaker=speaker,
            date=date_text,
            transcript_url=full_url,
            source_url=config.FED_SPEECHES_URL,
        )
        speeches.append(speech)
    
    return speeches

