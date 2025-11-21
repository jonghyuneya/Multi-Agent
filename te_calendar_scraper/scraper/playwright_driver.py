"""Utilities for launching and interacting with Playwright browsers."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from te_calendar_scraper import config


@asynccontextmanager
async def with_browser(headless: Optional[bool] = None) -> AsyncIterator[Browser]:
    """Async context manager yielding a configured Chromium browser instance."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=config.PLAYWRIGHT_HEADLESS if headless is None else headless
        )
        try:
            yield browser
        finally:
            await browser.close()


@asynccontextmanager
async def with_context(
    browser: Browser,
    *,
    user_agent: str | None = None,
    locale: str | None = None,
    timezone_id: str | None = None,
    viewport: dict | None = None,
    record_har_path: Optional[str] = None,
) -> AsyncIterator[BrowserContext]:
    """Create a new browser context with project defaults applied."""
    context = await browser.new_context(
        user_agent=user_agent or config.PLAYWRIGHT_USER_AGENT,
        locale=locale or config.PLAYWRIGHT_LOCALE,
        timezone_id=timezone_id or config.SITE_TIMEZONE_HINT,
        viewport=viewport or config.PLAYWRIGHT_VIEWPORT,
        record_har_path=record_har_path,
    )
    try:
        yield context
    finally:
        await context.close()


async def new_page(context: BrowserContext) -> Page:
    """Open a new page with sensible defaults."""
    page = await context.new_page()
    page.set_default_timeout(60_000)
    page.set_default_navigation_timeout(90_000)
    return page


async def wait_for_network_idle(page: Page, timeout: float = 30_000) -> None:
    """Wait for the network to be idle to stabilise the DOM."""
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        # Fallback: small delay to allow async data to settle.
        await asyncio.sleep(2)


