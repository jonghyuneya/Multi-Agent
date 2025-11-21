"""Structure probing utility for TradingEconomics indicator pages.

Run this script to log DOM snippets and selectors for indicator pages such as
CPI, EIA inventories, US Treasury yields, and ISM PMIs.
"""

from __future__ import annotations

import asyncio
import json
from typing import Iterable

from playwright.async_api import Page, async_playwright

INDICATOR_URLS = {
    "CPI YoY": "https://tradingeconomics.com/united-states/inflation-rate",
    "Core CPI": "https://tradingeconomics.com/united-states/core-inflation-rate",
    "Crude Inventories": "https://tradingeconomics.com/united-states/crude-oil-stocks-change",
    "NatGas Storage": "https://tradingeconomics.com/united-states/natural-gas-stocks-change",
    "UST Yields": "https://tradingeconomics.com/united-states/government-bond-yield",
    "ISM Manufacturing": "https://tradingeconomics.com/united-states/ism-manufacturing-pmi",
    "ISM Services": "https://tradingeconomics.com/united-states/ism-non-manufacturing-pmi",
}


async def log_value_tiles(page: Page) -> None:
    tile_selector = "div[class*='summary-container'], div.summary"
    tiles = page.locator(tile_selector)
    count = await tiles.count()
    print(f"[tiles] selector={tile_selector!r} count={count}")
    for idx in range(min(count, 2)):
        html = await tiles.nth(idx).inner_html()
        print(f"[tile {idx}] {html[:800]}")


async def log_stats_table(page: Page) -> None:
    table_selector = "table.table"
    tables = page.locator(table_selector)
    count = await tables.count()
    print(f"[tables] selector={table_selector!r} count={count}")
    for idx in range(min(count, 2)):
        html = await tables.nth(idx).inner_html()
        print(f"[table {idx}] {html[:800]}")


async def log_tabs(page: Page) -> None:
    tab_selector = "ul.nav-tabs li"
    tabs = page.locator(tab_selector)
    count = await tabs.count()
    texts = []
    for idx in range(count):
        text = await tabs.nth(idx).text_content()
        if text:
            texts.append(text.strip())
    print(f"[tabs] selector={tab_selector!r} -> {texts}")


async def capture_network(page: Page) -> None:
    async with page.expect_response(lambda resp: "chart" in resp.url.lower()) as future:
        try:
            resp = await asyncio.wait_for(future.value, timeout=5)
        except Exception:
            return
    try:
        data = await resp.json()
    except Exception:
        body = await resp.text()
        data = {"raw": body[:500]}
    print(f"[xhr] {resp.url}")
    print(json.dumps(data, indent=2)[:1200])


async def inspect_indicator(name: str, url: str) -> None:
    print("\n" + "=" * 80)
    print(f"[inspect] {name}: {url}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="UTC",
            viewport={"width": 1440, "height": 900},
        )
        page = await context.new_page()

        captured = []
        page.on(
            "response",
            lambda resp: captured.append(
                {
                    "url": resp.url,
                    "status": resp.status,
                    "resource": resp.request.resource_type,
                }
            )
            if resp.request.resource_type
            in (
                "xhr",
                "fetch",
                "script",
            )
            else None
        )
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(2_500)

        await log_tabs(page)
        await log_value_tiles(page)
        await log_stats_table(page)

        keywords = ("economics", "summary", "popup", "indicator", "chart", "series")
        print("[network]")
        for resp in captured:
            if any(keyword in resp["url"].lower() for keyword in keywords):
                print(f"  {resp['status']} {resp['resource']} {resp['url']}")

        await context.close()
        await browser.close()


async def main(urls: Iterable[tuple[str, str]]) -> None:
    for name, url in urls:
        await inspect_indicator(name, url)


if __name__ == "__main__":
    asyncio.run(main(INDICATOR_URLS.items()))


