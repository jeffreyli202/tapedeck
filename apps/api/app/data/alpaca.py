"""Alpaca historical data (free tier). The SDK is synchronous, so callers run
these in a thread."""

from __future__ import annotations

from datetime import date, datetime

from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import OptionHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import OptionBarsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from app.config import settings
from app.core.occ import OptionSpec
from app.core.pricer import list_expiries, strike_grid
from app.core.types import MARKET_CLOSE, MARKET_OPEN, Bar, et

OPTION_BATCH = 100


class AlpacaNotConfigured(RuntimeError):
    pass


def _keys() -> tuple[str, str]:
    if not settings.alpaca_api_key or not settings.alpaca_secret_key:
        raise AlpacaNotConfigured("Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env to ingest real data")
    return settings.alpaca_api_key, settings.alpaca_secret_key


def _regular_hours(ts: datetime) -> bool:
    t = et(ts).time()
    return MARKET_OPEN <= t < MARKET_CLOSE


def _convert(raw) -> Bar:
    return Bar(raw.timestamp, raw.open, raw.high, raw.low, raw.close, raw.volume or 0.0, raw.vwap)


def fetch_stock_bars(symbol: str, start: datetime, end: datetime) -> list[Bar]:
    client = StockHistoricalDataClient(*_keys())
    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
        feed=DataFeed(settings.alpaca_feed),
        adjustment=Adjustment.RAW,
    )
    data = client.get_stock_bars(req).data.get(symbol, [])
    return [_convert(b) for b in data if _regular_hours(b.timestamp)]


def contracts_for_day(underlying: str, day: date, spot: float, n_strikes: int = 10, max_dte: int = 7) -> list[OptionSpec]:
    return [
        OptionSpec(underlying, expiry, right, strike)
        for expiry in list_expiries(day, max_dte)
        for strike in strike_grid(spot, n_strikes)
        for right in ("C", "P")
    ]


def fetch_option_bars(specs: list[OptionSpec], start: datetime, end: datetime) -> list[tuple[str, Bar]]:
    client = OptionHistoricalDataClient(*_keys())
    out: list[tuple[str, Bar]] = []
    symbols = [s.symbol for s in specs]
    for i in range(0, len(symbols), OPTION_BATCH):
        req = OptionBarsRequest(
            symbol_or_symbols=symbols[i : i + OPTION_BATCH], timeframe=TimeFrame.Minute, start=start, end=end
        )
        for sym, bars in client.get_option_bars(req).data.items():
            out.extend((sym, _convert(b)) for b in bars if _regular_hours(b.timestamp))
    return out
