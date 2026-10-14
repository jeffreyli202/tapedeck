"""Daily VIX / VXN levels from CBOE, falling back to FRED (close only)."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime

import httpx

CBOE_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{index}_History.csv"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
FRED_SERIES = {"VIX": "VIXCLS", "VXN": "VXNCLS"}

Row = tuple[date, float | None, float | None]


def _num(v: str) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


async def fetch_cboe(index: str) -> list[Row]:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(CBOE_URL.format(index=index))
        resp.raise_for_status()
    rows = []
    for r in csv.DictReader(io.StringIO(resp.text)):
        d = datetime.strptime(r["DATE"], "%m/%d/%Y").date()
        rows.append((d, _num(r.get("OPEN")), _num(r.get("CLOSE"))))
    return rows


async def fetch_fred(index: str) -> list[Row]:
    series = FRED_SERIES[index]
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(FRED_URL.format(series=series))
        resp.raise_for_status()
    reader = csv.reader(io.StringIO(resp.text))
    next(reader)
    return [(date.fromisoformat(d), None, _num(v)) for d, v in reader if _num(v) is not None]


async def fetch_index(index: str) -> tuple[list[Row], str]:
    try:
        return await fetch_cboe(index), "cboe"
    except (httpx.HTTPError, KeyError, ValueError):
        return await fetch_fred(index), "fred"
