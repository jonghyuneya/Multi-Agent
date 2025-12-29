# TradingEconomics U.S. Economic Calendar Scraper

This project collects United States economic calendar events from the TradingEconomics website for a rolling window of +/-7 days relative to the current day in Asia/Seoul (`KST`). The scraper supports two operational modes:

- **DOM mode**: Uses Playwright to navigate the calendar page, apply filters, and extract rows from the rendered DOM.
- **XHR mode**: Replays the calendar's background JSON request discovered via Playwright and maps the payload to the project data model.

## Project Layout

```
te_calendar_scraper/
  ├── config.py
  ├── main.py
  ├── requirements.txt
  ├── README.md
  ├── probe_te_calendar.py
  ├── scraper/
  │    ├── calendar_dom.py
  │    ├── calendar_xhr.py
  │    ├── parse_utils.py
  │    └── playwright_driver.py
  ├── filters/
  │    └── event_filters.py
  └── io/
       ├── dedupe.py
       └── save_csv.py
```

## Getting Started

1. Install the dependencies:

   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

   > **Note:** in WSL or other minimal environments you may need extra system
   > libraries for Chromium. The repository includes the required `.deb`
   > archives—extract them locally and expose them via
   > `LD_LIBRARY_PATH=/path/to/extracted/usr/lib/x86_64-linux-gnu` when running
   > Playwright commands.

2. (Optional) Run the probing script to capture the latest DOM structure. The
   included selectors and XHR workflow were generated on 2025-11-12, but the
   probe is handy if TradingEconomics updates the calendar markup:

   ```bash
   python probe_te_calendar.py
   ```

3. Execute the scraper (choose between DOM, XHR, or indicators mode):

   ```bash
   python main.py --mode dom         # DOM calendar scraping
   python main.py --mode xhr         # XHR calendar scraping
   python main.py --mode indicators  # indicator headline collection
   ```

   The DOM mode launches Chromium via Playwright, injects the required cookies to
   filter by country/date/impact, waits for the table to render, and scrapes the
   rows directly. The XHR mode replays the cookie-controlled HTML request using
   `requests` + `BeautifulSoup` and parses the table server-side without
   launching a browser.

   Calendar modes output CSV files to `output/`, named
   `calendar_US_<start>_<end>.csv`. The indicators mode writes
   `indicators_US_<YYYYMMDD>.csv`, capturing CPI, EIA, UST yield, and ISM/PMI
   headline values via the same background XHRs used by the indicator pages.

## Notes

- The scraper uses only the website's DOM and its background network calls. It does **not** call the official TradingEconomics API.
- `config.py` holds selectors, cookie names, and other mutable settings captured
  during probing.
- The project aims to be polite: headless browsing, small random delays, and single-tab navigation.
- Times are parsed as UTC based on the site's hint (`SITE_TIMEZONE_HINT`) and
  converted to `Asia/Seoul` (KST). Events marked as "All Day" or "Tentative"
  keep a `None` timestamp but retain the raw time text.
- CSV columns include both UTC and KST timestamps, the event title, category,
  impact, country, raw time text, and source URL. Rows are deduplicated by the
  combination of `datetime_kst`, `title`, and `source_url`.


