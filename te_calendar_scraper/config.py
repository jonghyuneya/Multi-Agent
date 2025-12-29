"""Configuration constants and selectors for the TradingEconomics calendar scraper."""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Project metadata
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Scraper settings (to be refined after running the probe)
# ---------------------------------------------------------------------------

CALENDAR_ENTRY_URL = "https://tradingeconomics.com/united-states/interest-rate"
CALENDAR_URL = "https://tradingeconomics.com/calendar"

TZ_DISPLAY = "Asia/Seoul"
SITE_TIMEZONE_HINT = "UTC"

COUNTRY = "United States"
IMPACT_ALLOWED = {1, 2, 3}

# TradingEconomics chart infrastructure (used for indicator scraping)
TE_CHARTS_DATASOURCE = "https://d3ii0wo49og5mi.cloudfront.net"
TE_CHARTS_TOKEN = "20240229:nazare"
TE_OBFUSCATION_KEY = "tradingeconomics-charts-core-api-key"
# CSS selectors discovered via probing (used by DOM scraper)
ROW_SEL = "#calendar tr[data-country]"
TIME_SEL = "td:nth-of-type(1) span"
TITLE_SEL = "td:nth-of-type(3) a.calendar-event"
CATEGORY_SEL = "td:nth-of-type(3)"
IMPACT_SEL = "td:nth-of-type(1) span"
COUNTRY_SEL = None  # prefer row data attributes over text nodes
LINK_SEL = "td:nth-of-type(3) a.calendar-event"

# XHR scraping uses cookie-controlled HTML responses
XHR_URL_TEMPLATE = CALENDAR_URL
XHR_PARAM_KEYS = ("calendar-countries", "calendar-importance", "cal-custom-range")

# Default Playwright settings
PLAYWRIGHT_HEADLESS = True
PLAYWRIGHT_VIEWPORT = {"width": 1440, "height": 900}
PLAYWRIGHT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)
PLAYWRIGHT_LOCALE = "en-US"
REQUEST_USER_AGENT = PLAYWRIGHT_USER_AGENT

# Output
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Separate output directories for calendar and indicators
CALENDAR_OUTPUT_DIR = OUTPUT_DIR / "calendar"
CALENDAR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

INDICATOR_OUTPUT_DIR = OUTPUT_DIR / "indicators"
INDICATOR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Cookie configuration for calendar filters
CALENDAR_COOKIE_DOMAIN = "tradingeconomics.com"
CALENDAR_COUNTRY_COOKIE = "calendar-countries"
CALENDAR_IMPORTANCE_COOKIE = "calendar-importance"
CALENDAR_RANGE_COOKIE = "calendar-range"
CALENDAR_CUSTOM_RANGE_COOKIE = "cal-custom-range"

# Federal Reserve URLs
FOMC_BASE_URL = "https://www.federalreserve.gov"
FOMC_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FED_BASE_URL = "https://www.federalreserve.gov"
FED_SPEECHES_URL = "https://www.federalreserve.gov/newsevents/speeches.htm"

# Download directories
FOMC_DOWNLOADS_DIR = OUTPUT_DIR / "fomc_press_conferences"
FOMC_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
SPEECHES_DOWNLOADS_DIR = OUTPUT_DIR / "speeches_transcripts"
SPEECHES_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)


