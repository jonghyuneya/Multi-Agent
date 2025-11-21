"""DOM-based scraping utilities for the TradingEconomics calendar."""

from __future__ import annotations

from datetime import date
from typing import Dict, Iterable, List

from playwright.async_api import Page

import config
from scraper import parse_utils
from scraper.models import CalendarRow


async def goto_calendar(page: Page) -> None:
    """Navigate to the calendar page and wait for core scripts to load."""
    await page.goto(config.CALENDAR_URL, wait_until="domcontentloaded")
    await page.wait_for_function("typeof saveSelectionAndGO === 'function'")


async def apply_filters(
    page: Page,
    country_iso: str,
    start_date: date,
    end_date: date,
    impacts: Iterable[int],
) -> None:
    """Apply country and impact filters through the page's own helpers."""
    _ = (start_date, end_date)  # date range handled post-processing

    # Ensure all importance levels are active (triggers reload).
    impact_values = ",".join(str(i) for i in sorted(set(impacts))) or "1,2,3"
    await page.evaluate(
        "setCalendarImportance && setCalendarImportance(arguments[0]);",
        impact_values,
    )
    await page.wait_for_load_state("load")

    # Select the desired country via existing page helpers.
    selection_script = """
    (countryIso) => {
        if (typeof clearSelection === 'function') {
            clearSelection();
        }
        if (Array.isArray(window.selected_countries)) {
            window.selected_countries = [countryIso];
        } else {
            window.selected_countries = [countryIso];
        }
        if (typeof saveSelectionAndGO === 'function') {
            saveSelectionAndGO();
        }
    }
    """
    await page.evaluate(selection_script, country_iso.lower())
    await page.wait_for_load_state("load")


async def load_all_rows(page: Page) -> None:
    """The calendar renders synchronously; no extra pagination required."""
    await parse_utils.random_delay()


async def extract_rows_from_dom(
    page: Page,
    *,
    importance_map: Dict[str, int],
) -> List[CalendarRow]:
    """Extract calendar entries from the rendered DOM."""
    if not config.ROW_SEL or not config.TIME_SEL:
        raise RuntimeError("Selectors are not fully configured.")

    script = """
    ({ rowSel, timeSel, titleSel, linkSel }) => {
        const rows = Array.from(document.querySelectorAll(rowSel));
        return rows.map(row => {
            const timeSpan = timeSel ? row.querySelector(timeSel) : null;
            const timeText = timeSpan ? timeSpan.textContent.trim() : '';
            const timeClasses = timeSpan ? Array.from(timeSpan.classList) : [];
            const dateCell = timeSpan ? timeSpan.closest('td') : row.querySelector('td');
            const dateClasses = dateCell ? Array.from(dateCell.classList) : [];

            const titleAnchor = titleSel ? row.querySelector(titleSel) : null;
            const linkAnchor = linkSel ? row.querySelector(linkSel) : titleAnchor;

            const readText = (selector) => {
                const el = selector ? row.querySelector(selector) : null;
                return el ? el.textContent.trim() : '';
            };

            return {
                eventId: row.dataset.id || '',
                country: row.dataset.country || '',
                category: row.dataset.category || '',
                eventSlug: row.dataset.url || '',
                timeText,
                timeClasses,
                dateClasses,
                title: titleAnchor ? titleAnchor.textContent.trim() : '',
                href: linkAnchor ? linkAnchor.getAttribute('href') : '',
                actual: readText('#actual'),
                previous: readText('#previous'),
                consensus: readText('#consensus'),
                forecast: readText('#forecast'),
            };
        });
    }
    """

    raw_rows = await page.evaluate(
        script,
        {
            "rowSel": config.ROW_SEL,
            "timeSel": config.TIME_SEL,
            "titleSel": config.TITLE_SEL,
            "linkSel": config.LINK_SEL,
        },
    )

    calendar_rows: List[CalendarRow] = []
    for raw in raw_rows:
        event_id = raw.get("eventId")
        if not event_id:
            continue

        date_str = parse_utils.extract_date_from_classes(raw.get("dateClasses", []))
        dt_utc = parse_utils.parse_time_to_utc(raw.get("timeText"), date_str, config.SITE_TIMEZONE_HINT)
        dt_kst = parse_utils.to_kst(dt_utc)
        href = parse_utils.resolve_url(raw.get("href") or raw.get("eventSlug"))

        calendar_rows.append(
            CalendarRow(
                event_id=event_id,
                dt_utc=dt_utc,
                dt_kst=dt_kst,
                title=parse_utils.clean_text(raw.get("title")),
                category=parse_utils.clean_text(raw.get("category")),
                impact=importance_map.get(event_id),
                country=parse_utils.format_country(raw.get("country")),
                raw_time_text=parse_utils.clean_text(raw.get("timeText")),
                source_url=href,
                actual=parse_utils.clean_text(raw.get("actual")),
                previous=parse_utils.clean_text(raw.get("previous")),
                consensus=parse_utils.clean_text(raw.get("consensus")),
                forecast=parse_utils.clean_text(raw.get("forecast")),
            )
        )

    return calendar_rows


