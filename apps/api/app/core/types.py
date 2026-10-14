from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)
BAR_SECONDS = 60


@dataclass(slots=True)
class Bar:
    """A completed OHLCV bar. `ts` is the bar's start time (UTC, tz-aware)."""

    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    vwap: float | None = None

    @property
    def end(self) -> datetime:
        return self.ts + timedelta(seconds=BAR_SECONDS)

    def to_dict(self) -> dict:
        return {
            "t": int(self.ts.timestamp()),
            "o": self.open,
            "h": self.high,
            "l": self.low,
            "c": self.close,
            "v": self.volume,
            "vw": self.vwap,
        }


def et(ts: datetime) -> datetime:
    return ts.astimezone(ET)


def session_close(ts: datetime) -> datetime:
    local = et(ts)
    return datetime.combine(local.date(), MARKET_CLOSE, tzinfo=ET)


def minutes_since_open(ts: datetime) -> float:
    local = et(ts)
    opened = datetime.combine(local.date(), MARKET_OPEN, tzinfo=ET)
    return (local - opened).total_seconds() / 60


def minutes_to_close(ts: datetime) -> float:
    return (session_close(ts) - ts).total_seconds() / 60
