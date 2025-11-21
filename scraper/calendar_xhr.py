"""XHR-based scraping for the TradingEconomics calendar."""

from __future__ import annotations

from datetime import date
from typing import Dict, Iterable, List, Optional, Set

import requests
from bs4 import BeautifulSoup
from playwright.async_api import Page

import config
from scraper import parse_utils
from scraper.models import CalendarRow

REQUEST_HEADERS = {
    "User-Agent": config.PLAYWRIGHT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": config.CALENDAR_URL,
}


async def discover_calendar_xhr(page: Page) -> tuple[str, Dict[str, str]]:
    """Return the reusable calendar URL and an empty params schema."""
    return config.XHR_URL_TEMPLATE, {}


def _fetch_calendar_html(extra_cookies: Optional[Dict[str, str]] = None) -> str:
    cookies = {"calendar-countries": config.COUNTRY_ISO}
    if extra_cookies:
        cookies.update(extra_cookies)
    response = requests.get(
        config.XHR_URL_TEMPLATE,
        headers=REQUEST_HEADERS,
        cookies=cookies,
        timeout=30,
    )
    response.raise_for_status()
    return response.text


def build_importance_lookup() -> Dict[str, int]:
    """Return a mapping of event id -> impact level (1..3)."""
    ids_level3 = _collect_event_ids_for_importance("3")
    ids_level2 = _collect_event_ids_for_importance("2")
    ids_level1 = _collect_event_ids_for_importance("1")

    importance_map: Dict[str, int] = {}

    for event_id in ids_level1:
        importance_map[event_id] = 1
    for event_id in ids_level2:
        importance_map[event_id] = 2
    for event_id in ids_level3:
        importance_map[event_id] = 3

    return importance_map


def _collect_event_ids_for_importance(level: str) -> Set[str]:
    html = _fetch_calendar_html({"calendar-importance": level})
    soup = BeautifulSoup(html, "html.parser")
    ids = {row.get("data-id") for row in soup.select(config.ROW_SEL)}
    return {event_id for event_id in ids if event_id}


def fetch_calendar_rows(
    start_date: date,
    end_date: date,
    *,
    importance_map: Dict[str, int],
) -> List[CalendarRow]:
    """Fetch and parse calendar entries using direct HTTP requests."""
    _ = (start_date, end_date)  # Filtering handled downstream
    html = _fetch_calendar_html({"calendar-importance": "1,2,3"})
    soup = BeautifulSoup(html, "html.parser")
    rows: List[CalendarRow] = []

    for tr in soup.select(config.ROW_SEL):
        event_id = tr.get("data-id")
        if not event_id:
            continue

        time_span = tr.select_one(config.TIME_SEL) if config.TIME_SEL else None
        date_cell = time_span.find_parent("td") if time_span else tr.find("td")

        date_classes = date_cell.get("class", []) if date_cell else []
        date_str = parse_utils.extract_date_from_classes(date_classes)
        time_text = parse_utils.clean_text(time_span.text if time_span else None)

        dt_utc = parse_utils.parse_time_to_utc(time_text, date_str, config.SITE_TIMEZONE_HINT)
        dt_kst = parse_utils.to_kst(dt_utc)

        title_el = tr.select_one(config.TITLE_SEL) if config.TITLE_SEL else None
        link_el = tr.select_one(config.LINK_SEL) if config.LINK_SEL else None
        href = parse_utils.resolve_url(
            (link_el.get("href") if link_el else None)
            or tr.get("data-url")
        )

        rows.append(
            CalendarRow(
                event_id=event_id,
                dt_utc=dt_utc,
                dt_kst=dt_kst,
                title=parse_utils.clean_text(title_el.text if title_el else None) or "",
                category=parse_utils.clean_text(tr.get("data-category")),
                impact=importance_map.get(event_id),
                country=parse_utils.format_country(tr.get("data-country")),
                raw_time_text=time_text,
                source_url=href,
                actual=parse_utils.clean_text(_select_text(tr, "#actual")),
                previous=parse_utils.clean_text(_select_text(tr, "#previous")),
                consensus=parse_utils.clean_text(_select_text(tr, "#consensus")),
                forecast=parse_utils.clean_text(_select_text(tr, "#forecast")),
            )
        )

    return rows


def _select_text(root: BeautifulSoup, selector: str) -> Optional[str]:
    element = root.select_one(selector)
    return element.text if element else None


