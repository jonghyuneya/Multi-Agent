"""Utilities for downloading files with skip logic for already downloaded files."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

from te_calendar_scraper import config

logger = logging.getLogger(__name__)


def get_filename_from_url(url: str, default_name: str = "download") -> str:
    """Extract filename from URL or generate a default one."""
    parsed = urlparse(url)
    path = parsed.path
    if path:
        filename = Path(path).name
        if filename and '.' in filename:
            return filename
    
    # If no filename in URL, try to get from Content-Disposition header
    # or use default
    return default_name


def download_file(
    url: str,
    output_dir: Path,
    filename: Optional[str] = None,
    skip_existing: bool = True,
) -> Optional[Path]:
    """
    Download a file from URL to output directory.
    
    Args:
        url: URL to download from
        output_dir: Directory to save the file
        filename: Optional filename. If not provided, extracted from URL
        skip_existing: If True, skip download if file already exists
    
    Returns:
        Path to downloaded file, or None if skipped or failed
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not filename:
        filename = get_filename_from_url(url)
    
    output_path = output_dir / filename
    
    # Skip if file already exists
    if skip_existing and output_path.exists():
        logger.info(f"Skipping {filename} - already exists")
        return output_path
    
    try:
        response = requests.get(
            url,
            headers={"User-Agent": config.REQUEST_USER_AGENT},
            timeout=30,
            stream=True,
        )
        response.raise_for_status()
        
        # Write file
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        logger.info(f"Downloaded {filename} to {output_path}")
        return output_path
    
    except requests.RequestException as e:
        logger.error(f"Failed to download {url}: {e}")
        return None


def download_pdf_with_metadata(
    url: str,
    output_dir: Path,
    metadata: dict,
    skip_existing: bool = True,
) -> Optional[Path]:
    """
    Download a PDF file with metadata-based filename.
    
    Args:
        url: URL to download from
        output_dir: Directory to save the file
        metadata: Dictionary with metadata to include in filename (e.g., year, month, dates)
        skip_existing: If True, skip download if file already exists
    
    Returns:
        Path to downloaded file, or None if skipped or failed
    """
    # Generate filename from metadata
    parts = []
    if 'year' in metadata:
        parts.append(str(metadata['year']))
    if 'month' in metadata:
        parts.append(metadata['month'])
    if 'dates' in metadata:
        parts.append(metadata['dates'].replace('-', '_'))
    if 'title' in metadata:
        # Clean title for filename
        title = re.sub(r'[^\w\s-]', '', metadata['title'])[:50]
        parts.append(title.replace(' ', '_'))
    
    if parts:
        filename = '_'.join(parts) + '.pdf'
    else:
        filename = get_filename_from_url(url)
    
    return download_file(url, output_dir, filename, skip_existing)


def download_html_file(
    url: str,
    output_dir: Path,
    filename: Optional[str] = None,
    skip_existing: bool = True,
) -> Optional[Path]:
    """
    Download an HTML file from URL to output directory.
    
    Args:
        url: URL to download from
        output_dir: Directory to save the file
        filename: Optional filename. If not provided, extracted from URL
        skip_existing: If True, skip download if file already exists
    
    Returns:
        Path to downloaded file, or None if skipped or failed
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not filename:
        filename = get_filename_from_url(url, "transcript.html")
        # Ensure .html extension
        if not filename.endswith('.html'):
            filename = filename.rsplit('.', 1)[0] + '.html'
    
    output_path = output_dir / filename
    
    # Skip if file already exists
    if skip_existing and output_path.exists():
        logger.info(f"Skipping {filename} - already exists")
        return output_path
    
    try:
        response = requests.get(
            url,
            headers={"User-Agent": config.REQUEST_USER_AGENT},
            timeout=30,
        )
        response.raise_for_status()
        
        # Ensure we're getting HTML content
        content = response.content
        
        # Try to decode as text to handle encoding issues
        try:
            # Try UTF-8 first
            text_content = content.decode('utf-8')
        except UnicodeDecodeError:
            # Try to detect encoding from response headers
            encoding = response.encoding or 'utf-8'
            try:
                text_content = content.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                # Fallback to latin-1 which can decode any byte
                text_content = content.decode('latin-1')
        
        # Write file as UTF-8
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(text_content)
        
        logger.info(f"Downloaded {filename} to {output_path}")
        return output_path
    
    except requests.RequestException as e:
        logger.error(f"Failed to download {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error processing {url}: {e}")
        return None

