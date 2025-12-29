"""Cookie-driven HTTP scraping for the TradingEconomics calendar."""

from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Dict, Iterable, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from playwright.async_api import Page

from te_calendar_scraper import config
from te_calendar_scraper.scraper import parse_utils
from te_calendar_scraper.scraper.models import CalendarRow

DEFAULT_HEADERS = {
    "User-Agent": config.PLAYWRIGHT_USER_AGENT,
    "Referer": config.CALENDAR_URL,
    "Origin": "https://tradingeconomics.com",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}

_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


async def discover_calendar_xhr(page: Page) -> tuple[str, Dict[str, str]]:
    """Return the base URL for cookie-driven calendar requests."""
    _ = page  # Playwright page currently unused – retained for parity with DOM mode.
    if not config.XHR_URL_TEMPLATE:
        raise RuntimeError("XHR_URL_TEMPLATE not yet configured. Run the probe.")
    return config.XHR_URL_TEMPLATE, {}


def build_cookie_payload(
    country: str,
    start_date: date,
    end_date: date,
    impacts: Iterable[int],
) -> Dict[str, str]:
    """Construct the cookie dictionary needed to filter the calendar server-side."""
    return {
        config.CALENDAR_COUNTRY_COOKIE: _country_to_cookie(country),
        config.CALENDAR_IMPORTANCE_COOKIE: ",".join(str(i) for i in sorted(set(impacts))),
        config.CALENDAR_RANGE_COOKIE: "0",
        config.CALENDAR_CUSTOM_RANGE_COOKIE: f"{start_date:%Y-%m-%d}|{end_date:%Y-%m-%d}",
    }


def fetch_calendar_rows(url: str, cookies: Dict[str, str]) -> List[CalendarRow]:
    """Fetch the filtered HTML calendar and normalise the rows."""
    response = requests.get(url, headers=DEFAULT_HEADERS, cookies=cookies, timeout=30)
    response.raise_for_status()
    return _parse_calendar_html(response.text)


def _parse_calendar_html(html: str) -> List[CalendarRow]:
    soup = BeautifulSoup(html, "lxml")
    rows: List[CalendarRow] = []
    last_event_date: Optional[date] = None

    for tr in soup.select(config.ROW_SEL):
        if not tr.get("data-id"):
            continue

        event_date = _extract_row_date(tr)
        if event_date is None:
            event_date = last_event_date
        else:
            last_event_date = event_date

        time_cell = tr.find("td")
        if time_cell is None:
            continue

        time_span = time_cell.find("span")
        raw_time = parse_utils.clean_text(time_span.get_text(" ", strip=True) if time_span else None)

        title_cell = _safe_get_cell(tr, 2)
        title = parse_utils.clean_text(title_cell.get_text(" ", strip=True) if title_cell else None) or ""

        category_attr = tr.get("data-category")
        category = parse_utils.clean_text(category_attr.title() if category_attr else None)
        country_attr = tr.get("data-country")
        country = parse_utils.clean_text(country_attr.title() if country_attr else None)

        source_anchor = title_cell.find("a", class_="calendar-event") if title_cell else None
        href = source_anchor.get("href") if source_anchor else None
        source_url = urljoin(config.CALENDAR_URL, href) if href else None

        impact = _extract_impact(time_span)

        context_dt = datetime.combine(event_date, time.min) if event_date else None
        dt_utc = parse_utils.parse_time_to_utc(raw_time, context_dt)
        dt_kst = parse_utils.to_kst(dt_utc)

        rows.append(
            CalendarRow(
                dt_utc=dt_utc,
                dt_kst=dt_kst,
                title=title,
                category=category,
                impact=impact,
                country=country,
                raw_time_text=raw_time,
                source_url=source_url,
            )
        )

    return rows


def _safe_get_cell(tr, index: int):
    cells = tr.find_all("td")
    if index < len(cells):
        return cells[index]
    return None


def _extract_row_date(tr) -> Optional[date]:
    time_cell = tr.find("td")
    if not time_cell:
        return None
    class_attr = time_cell.get("class")
    if isinstance(class_attr, list):
        class_str = " ".join(class_attr)
    else:
        class_str = class_attr or ""
    match = _DATE_PATTERN.search(class_str)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _extract_impact(time_span) -> Optional[int]:
    if time_span is None:
        return None
    class_attr = time_span.get("class", [])
    if isinstance(class_attr, str):
        class_tokens = class_attr.split()
    else:
        class_tokens = class_attr
    for token in class_tokens:
        if token.startswith("calendar-date-"):
            suffix = token.split("-")[-1]
            if suffix.isdigit():
                return int(suffix)
        if token.startswith("importance-"):
            suffix = token.split("-")[-1]
            if suffix.isdigit():
                return int(suffix)
    return None


def _country_to_cookie(country: str) -> str:
    canonical = country.strip().lower()
    if canonical in ("united states", "us", "usa", "u.s.", "u.s.a."):
        return "usa"
    return canonical.replace(" ", "-")



