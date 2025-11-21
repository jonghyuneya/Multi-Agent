"""DOM-based scraping utilities for the TradingEconomics calendar."""

from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Iterable, List, Optional
from urllib.parse import urljoin

from playwright.async_api import Locator, Page

from te_calendar_scraper import config
from te_calendar_scraper.scraper import parse_utils
from te_calendar_scraper.scraper.models import CalendarRow

_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


async def goto_calendar(page: Page) -> None:
    """Navigate the page to the calendar entry URL."""
    await page.goto(config.CALENDAR_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(1_000)
    await parse_utils.random_delay()


async def apply_filters(
    page: Page,
    country: str,
    start_date: date,
    end_date: date,
    impacts: Iterable[int],
) -> None:
    """Persist calendar filters via cookies and refresh the page."""
    country_cookie = _country_to_cookie(country)
    impacts_cookie = ",".join(str(i) for i in sorted(set(impacts)))
    custom_range = f"{start_date:%Y-%m-%d}|{end_date:%Y-%m-%d}"

    await page.context.add_cookies(
        [
            {
                "name": config.CALENDAR_COUNTRY_COOKIE,
                "value": country_cookie,
                "domain": config.CALENDAR_COOKIE_DOMAIN,
                "path": "/",
                "secure": True,
                "httpOnly": False,
                "sameSite": "None",
            },
            {
                "name": config.CALENDAR_IMPORTANCE_COOKIE,
                "value": impacts_cookie,
                "domain": config.CALENDAR_COOKIE_DOMAIN,
                "path": "/",
                "secure": True,
                "httpOnly": False,
                "sameSite": "None",
            },
            {
                "name": config.CALENDAR_RANGE_COOKIE,
                "value": "0",
                "domain": config.CALENDAR_COOKIE_DOMAIN,
                "path": "/",
                "secure": True,
                "httpOnly": False,
                "sameSite": "None",
            },
            {
                "name": config.CALENDAR_CUSTOM_RANGE_COOKIE,
                "value": custom_range,
                "domain": config.CALENDAR_COOKIE_DOMAIN,
                "path": "/",
                "secure": True,
                "httpOnly": False,
                "sameSite": "None",
            },
        ]
    )

    await page.reload(wait_until="domcontentloaded")
    try:
        await page.wait_for_load_state("networkidle")
    except Exception:
        await parse_utils.random_delay(400, 700)
    await parse_utils.random_delay(500, 900)


async def load_all_rows(page: Page) -> None:
    """Attempt to reveal all table rows (click any 'load more' affordances)."""
    load_more_selectors = (
        "button:has-text('Load More')",
        "button:has-text('More Events')",
        "a:has-text('Load More')",
    )
    for selector in load_more_selectors:
        while True:
            locator = page.locator(selector)
            try:
                if await locator.count() == 0 or not await locator.first.is_visible():
                    break
                await locator.first.click()
                await parse_utils.random_delay(400, 800)
                try:
                    await page.wait_for_load_state("networkidle", timeout=15_000)
                except Exception:
                    await parse_utils.random_delay(400, 700)
            except Exception:
                break


async def extract_rows_from_dom(page: Page) -> List[CalendarRow]:
    """Extract calendar rows from the DOM using configured selectors."""
    if not config.ROW_SEL:
        raise RuntimeError("ROW_SEL is not configured. Run the probe first.")

    rows: List[CalendarRow] = []
    last_event_date: Optional[date] = None

    row_locator = page.locator(config.ROW_SEL)
    row_count = await row_locator.count()
    for idx in range(row_count):
        row = row_locator.nth(idx)
        if not await _is_data_row(row):
            continue

        event_date = await _extract_row_date(row)
        if event_date is None:
            event_date = last_event_date
        else:
            last_event_date = event_date

        raw_time = await parse_utils.locator_text(row, config.TIME_SEL)
        title = parse_utils.clean_text(await parse_utils.locator_text(row, config.TITLE_SEL) or "")
        if not title:
            continue

        category_attr = await row.get_attribute("data-category")
        category = parse_utils.clean_text(category_attr.title() if category_attr else None)

        country_attr = await row.get_attribute("data-country")
        country = parse_utils.clean_text(country_attr.title() if country_attr else None)

        impact_value = await parse_utils.extract_impact(row, config.IMPACT_SEL)
        source_url = await parse_utils.locator_href(row, config.LINK_SEL)
        source_url = urljoin(config.CALENDAR_URL, source_url) if source_url else None

        context_dt = datetime.combine(event_date, time.min) if event_date else None
        dt_utc = parse_utils.parse_time_to_utc(raw_time, context_dt)
        dt_kst = parse_utils.to_kst(dt_utc)

        rows.append(
            CalendarRow(
                dt_utc=dt_utc,
                dt_kst=dt_kst,
                title=title,
                category=category,
                impact=impact_value,
                country=country,
                raw_time_text=parse_utils.clean_text(raw_time),
                source_url=source_url,
            )
        )

    return rows


async def _is_data_row(row: Locator) -> bool:
    """Return True if the row carries calendar data."""
    data_id = await row.get_attribute("data-id")
    return data_id is not None


async def _extract_row_date(row: Locator) -> Optional[date]:
    """Parse the ISO date embedded within the first column class attribute."""
    try:
        first_cell = row.locator("td").first
        class_attr = await first_cell.get_attribute("class") or ""
    except Exception:
        return None

    match = _DATE_PATTERN.search(class_attr)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _country_to_cookie(country: str) -> str:
    """Map a human readable country name to the cookie-expected token."""
    canonical = country.strip().lower()
    if canonical in ("united states", "us", "usa", "u.s.", "u.s.a."):
        return "usa"
    return canonical.replace(" ", "-")



