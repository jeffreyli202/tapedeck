"""Synthetic minute bars and vol-index levels so the app is usable before any
Alpaca keys are configured. Rows are tagged source="synthetic" and never
overwrite real data."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import numpy as np

from app.core.types import ET, MARKET_OPEN, Bar

START_PRICE = {"SPY": 520.0, "QQQ": 445.0}
VOL_INDEX = {"SPY": "VIX", "QQQ": "VXN"}
MINUTES = 390


def weekdays_back(end: date, n: int) -> list[date]:
    days: list[date] = []
    d = end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return days[::-1]


def generate(symbol: str, days: list[date], seed: int = 7) -> tuple[list[Bar], list[tuple[date, float, float]]]:
    rng = np.random.default_rng(seed + sum(map(ord, symbol)))
    price = START_PRICE.get(symbol, 100.0)
    vix = 15.0 if symbol == "SPY" else 19.0
    minutes = np.arange(MINUTES)
    # U-shaped intraday volatility and volume profile.
    shape = 1 + 1.2 * np.exp(-minutes / 25) + 0.6 * np.exp(-(MINUTES - minutes) / 30)
    shape /= shape.mean()
    bars: list[Bar] = []
    iv_rows = []
    for day in days:
        vix_open = vix
        vix = max(9.0, vix + 0.15 * (17 - vix) + rng.normal(0, 1.2))
        iv_rows.append((day, round(vix_open, 2), round(vix, 2)))
        daily_sigma = vix_open / 100 / math.sqrt(252)
        sigma = daily_sigma / math.sqrt(MINUTES) * shape
        drift = rng.normal(0.0002, daily_sigma * 0.3) / MINUTES
        rets = drift + sigma * rng.standard_t(5, MINUTES) / math.sqrt(5 / 3)
        price *= 1 + rng.normal(0, daily_sigma * 0.25)  # overnight gap
        opened = datetime.combine(day, MARKET_OPEN, tzinfo=ET)
        for i in range(MINUTES):
            o = price
            c = o * (1 + rets[i])
            wick = abs(rng.normal(0, sigma[i] * 0.6)) * o
            h, low = max(o, c) + wick, min(o, c) - abs(rng.normal(0, sigma[i] * 0.6)) * o
            vol = float(rng.gamma(4, 30_000 * shape[i]))
            typical = (h + low + c) / 3
            bars.append(
                Bar(opened + timedelta(minutes=i), round(o, 2), round(h, 2), round(low, 2), round(c, 2),
                    round(vol), round(typical, 4))
            )
            price = c
    return bars, iv_rows
