"""Indicator scraping routines for TradingEconomics indicator pages.

The TradingEconomics indicator pages fetch their headline values via
`https://d3ii0wo49og5mi.cloudfront.net/economics/<symbol>` requests.  The
payload is a base64-encoded, XOR-obfuscated, deflate-compressed JSON blob.

This module replays those requests (no official API usage) and normalises the
results into `IndicatorRow` records.
"""

from __future__ import annotations

import base64
import json
import logging
import math
import zlib
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence
from urllib.parse import quote

import requests

from te_calendar_scraper import config
from te_calendar_scraper.scraper.models import IndicatorRow

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Indicator target configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorTarget:
    bucket: str
    name: str
    symbol: str
    source_url: str
    params: Optional[Dict[str, str]] = None


CPI_TARGETS: Sequence[IndicatorTarget] = (
    IndicatorTarget(
        bucket="CPI",
        name="CPI YoY",
        symbol="cpi yoy",
        source_url="https://tradingeconomics.com/united-states/inflation-cpi",
    ),
    IndicatorTarget(
        bucket="CPI",
        name="CPI MoM",
        symbol="unitedstainfratmom",
        source_url="https://tradingeconomics.com/united-states/inflation-rate-mom",
    ),
    IndicatorTarget(
        bucket="CPI",
        name="Core CPI YoY",
        symbol="usacorecpirate",
        source_url="https://tradingeconomics.com/united-states/core-inflation-rate",
    ),
    IndicatorTarget(
        bucket="CPI",
        name="Core CPI MoM",
        symbol="usacirm",
        source_url="https://tradingeconomics.com/united-states/core-inflation-rate-mom",
    ),
)

EIA_TARGETS: Sequence[IndicatorTarget] = (
    IndicatorTarget(
        bucket="EIA",
        name="Crude Oil Inventories",
        symbol="unitedstacruoilstoch",
        source_url="https://tradingeconomics.com/united-states/crude-oil-stocks-change",
    ),
    IndicatorTarget(
        bucket="EIA",
        name="Gasoline Inventories",
        symbol="unitedstagasstocha",
        source_url="https://tradingeconomics.com/united-states/gasoline-stocks-change",
    ),
    IndicatorTarget(
        bucket="EIA",
        name="Distillate Inventories",
        symbol="unitedstadissto",
        source_url="https://tradingeconomics.com/united-states/distillate-fuel-oil-stocks-change",
    ),
    IndicatorTarget(
        bucket="EIA",
        name="Natural Gas Storage",
        symbol="unitedstanatgasstoch",
        source_url="https://tradingeconomics.com/united-states/natural-gas-stocks-change",
    ),
)

UST_TARGETS: Sequence[IndicatorTarget] = (
    IndicatorTarget(
        bucket="UST",
        name="US 3M Yield",
        symbol="usgg3m:ind",
        source_url="https://tradingeconomics.com/united-states/government-bond-yield",
    ),
    IndicatorTarget(
        bucket="UST",
        name="US 2Y Yield",
        symbol="usgg2yr:ind",
        source_url="https://tradingeconomics.com/united-states/government-bond-yield",
    ),
    IndicatorTarget(
        bucket="UST",
        name="US 5Y Yield",
        symbol="usgg5yr:ind",
        source_url="https://tradingeconomics.com/united-states/government-bond-yield",
    ),
    IndicatorTarget(
        bucket="UST",
        name="US 10Y Yield",
        symbol="usgg10yr:ind",
        source_url="https://tradingeconomics.com/united-states/government-bond-yield",
    ),
    IndicatorTarget(
        bucket="UST",
        name="US 30Y Yield",
        symbol="usgg30y:ind",
        source_url="https://tradingeconomics.com/united-states/government-bond-yield",
    ),
)

ISM_TARGETS: Sequence[IndicatorTarget] = (
    IndicatorTarget(
        bucket="ISM",
        name="ISM Manufacturing PMI",
        symbol="unitedstamanpmi",
        source_url="https://tradingeconomics.com/united-states/manufacturing-pmi",
    ),
    IndicatorTarget(
        bucket="ISM",
        name="ISM Services PMI",
        symbol="unitedstaserpmi",
        source_url="https://tradingeconomics.com/united-states/services-pmi",
    ),
    IndicatorTarget(
        bucket="ISM",
        name="ISM Composite PMI",
        symbol="unitedstacompmi",
        source_url="https://tradingeconomics.com/united-states/composite-pmi",
    ),
)

ALL_INDICATOR_TARGETS: Sequence[IndicatorTarget] = (
    *CPI_TARGETS,
    *EIA_TARGETS,
    *UST_TARGETS,
    *ISM_TARGETS,
)

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _decode_payload(text: str) -> Optional[dict]:
    """Decode the TradingEconomics series payload."""

    try:
        raw = base64.b64decode(text)
        key_bytes = config.TE_OBFUSCATION_KEY.encode()
        xored = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(raw))
        inflated = zlib.decompress(xored, 31).decode("utf-8")
        return json.loads(inflated)
    except Exception as exc:  # pragma: no cover - defensive branch
        logger.warning("Failed to decode payload: %s", exc)
        return None


def _fetch_series(
    symbol: str, params: Optional[Dict[str, str]] = None
) -> tuple[Optional[dict], Optional[str]]:
    """Return the decoded series dict for a given symbol."""

    base_params = {"n": "12", "key": config.TE_CHARTS_TOKEN}
    if params:
        base_params.update(params)

    encoded_symbol = quote(symbol.lower(), safe=":")
    url = f"{config.TE_CHARTS_DATASOURCE}/economics/{encoded_symbol}"

    try:
        resp = requests.get(
            url,
            params=base_params,
            headers={"User-Agent": config.REQUEST_USER_AGENT},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Request error for %s: %s", symbol, exc)
        return None, f"request-error: {exc}"

    decoded = _decode_payload(resp.text)
    if not decoded:
        return None, "decode-error"

    series_list = decoded[0].get("series") if decoded else None
    if not series_list:
        return None, "empty-series"

    serie = series_list[0].get("serie")
    if not serie:
        return None, "missing-serie"

    return serie, None


def _format_value(value: Optional[float]) -> Optional[str]:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return None
    if isinstance(value, int):
        return str(value)
    try:
        return f"{value:.6f}".rstrip("0").rstrip(".")
    except Exception:  # pragma: no cover - defensive
        return str(value)


def _compute_day_change(serie: dict) -> Optional[str]:
    freq = (serie.get("frequency") or "").lower()
    if "day" not in freq or "data" not in serie:
        return None
    data = serie["data"]
    if not isinstance(data, list) or len(data) < 2:
        return None
    last, prev = data[-1][0], data[-2][0]
    if last is None or prev is None:
        return None
    return _format_value(float(last) - float(prev))


def _extract_latest_row(
    target: IndicatorTarget,
) -> IndicatorRow:
    serie, error = _fetch_series(target.symbol, target.params)

    if not serie or error:
        note = error or "unknown-error"
        return IndicatorRow(
            indicator_bucket=target.bucket,
            indicator_name=target.name,
            latest_value=None,
            unit=None,
            day_change=None,
            month_change=None,
            year_change=None,
            obs_date=None,
            source_url=target.source_url,
            raw_source_note=f"symbol={target.symbol}; {note}",
        )

    data = serie.get("data") or []
    latest_value = None
    obs_date = None
    if data:
        last_entry = data[-1]
        if isinstance(last_entry, (list, tuple)) and last_entry:
            latest_value = _format_value(last_entry[0])
            if len(last_entry) >= 4:
                obs_date = last_entry[3]

    day_change = _compute_day_change(serie)

    note_parts = [
        f"symbol={target.symbol}",
        f"points={len(data)}",
        f"frequency={serie.get('frequency')}",
    ]
    raw_note = "; ".join(note_parts)

    return IndicatorRow(
        indicator_bucket=target.bucket,
        indicator_name=target.name,
        latest_value=latest_value,
        unit=serie.get("unit"),
        day_change=day_change,
        month_change=None,
        year_change=None,
        obs_date=obs_date,
        source_url=target.source_url,
        raw_source_note=raw_note,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def collect_indicators() -> List[IndicatorRow]:
    """Collect indicator rows for all configured targets."""

    rows: List[IndicatorRow] = []
    for target in ALL_INDICATOR_TARGETS:
        row = _extract_latest_row(target)
        rows.append(row)
    return rows



