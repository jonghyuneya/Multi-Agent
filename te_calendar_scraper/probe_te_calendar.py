import asyncio
import json
import re

from playwright.async_api import async_playwright


CAL_URL = "https://tradingeconomics.com/calendar"

ROW_SAMPLE_COUNT = 5


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="UTC",
        )
        page = await ctx.new_page()

        xhrs = []

        def capture_response(resp):
            if resp.request.resource_type in ("xhr", "fetch"):
                xhrs.append(
                    {
                        "url": resp.url,
                        "status": resp.status,
                        "type": resp.request.resource_type,
                    }
                )

        page.on("response", capture_response)

        await page.goto(CAL_URL, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=60000)
        except Exception as exc:
            print(f"[warn] wait_for_load_state networkidle timeout: {exc}")

        candidates = [
            "tbody tr",
            "table tr",
            "div[role='row']",
            ".calendar-table tr",
            ".calendar-table [role='row']",
            "[data-cal-event]",
            "table[id] tbody tr",
        ]

        for sel in candidates:
            try:
                count = await page.locator(sel).count()
                if count:
                    print(f"[DOM] '{sel}' -> {count} rows")
            except Exception as exc:
                print(f"[DOM] '{sel}' error: {exc}")

        table_ids = await page.evaluate(
            "Array.from(document.querySelectorAll('table[id]')).map(t => ({id: t.id, rows: t.querySelectorAll('tr').length}))"
        )
        print("[tables with id]")
        print(json.dumps(table_ids, indent=2))

        row_sel = "#calendar tr[data-country]"
        rows = page.locator(row_sel)
        row_count = await rows.count()
        print(f"[DOM] using row selector '{row_sel}' -> {row_count} rows")

        for i in range(min(row_count, ROW_SAMPLE_COUNT)):
            row = rows.nth(i)
            attrs = {
                "class": await row.get_attribute("class"),
                "text": await row.inner_text(),
                "html": await row.inner_html(),
            }
            print("=" * 30)
            print(json.dumps(attrs, indent=2)[:1600])

        print("\n[XHR candidates]")
        for x in xhrs:
            if re.search(r"calendar|start|end|country|importance", x["url"], re.I):
                print(f"{x['status']} {x['type']} {x['url']}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
