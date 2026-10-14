"""Database reads/writes for market data plus in-memory lookups the core uses."""

from __future__ import annotations

import bisect
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.types import ET, MARKET_CLOSE, MARKET_OPEN, Bar
from app.db import engine
from app.models import BarRow, IvDaily, OptionBarRow, OptionContract

TIMEFRAMES = {"1m": "bars", "5m": "bars_5m", "15m": "bars_15m", "1h": "bars_1h"}
STALE_OPTION_BAR = timedelta(minutes=15)
CHUNK = 2000


def day_bounds(day: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(day, MARKET_OPEN, tzinfo=ET),
        datetime.combine(day, MARKET_CLOSE, tzinfo=ET),
    )


def range_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return day_bounds(start)[0], day_bounds(end)[1]


def _to_bar(r) -> Bar:
    return Bar(r.ts, r.open, r.high, r.low, r.close, r.volume or 0.0, r.vwap)


async def load_bars(
    db: AsyncSession, symbol: str, start: datetime, end: datetime, timeframe: str = "1m"
) -> list[Bar]:
    table = TIMEFRAMES[timeframe]
    rows = await db.execute(
        text(
            f"SELECT ts, open, high, low, close, volume, vwap FROM {table} "
            "WHERE symbol = :s AND ts >= :a AND ts < :b ORDER BY ts"
        ),
        {"s": symbol, "a": start, "b": end},
    )
    return [_to_bar(r) for r in rows]


async def upsert_bars(
    db: AsyncSession, symbol: str, bars: list[Bar], source: str, overwrite: bool = True
) -> int:
    for i in range(0, len(bars), CHUNK):
        chunk = bars[i : i + CHUNK]
        stmt = insert(BarRow).values(
            [
                dict(symbol=symbol, ts=b.ts, open=b.open, high=b.high, low=b.low, close=b.close,
                     volume=b.volume, vwap=b.vwap, source=source)
                for b in chunk
            ]
        )
        if overwrite:
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol", "ts"],
                set_={c: stmt.excluded[c] for c in ("open", "high", "low", "close", "volume", "vwap", "source")},
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=["symbol", "ts"])
        await db.execute(stmt)
    await db.commit()
    return len(bars)


async def refresh_aggregates(start: datetime, end: datetime) -> None:
    # Continuous aggregate refreshes cannot run inside a transaction.
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        for view in ("bars_5m", "bars_15m", "bars_1h"):
            await conn.execute(
                text(f"CALL refresh_continuous_aggregate('{view}', CAST(:a AS timestamptz), CAST(:b AS timestamptz))"),
                {"a": start - timedelta(hours=1), "b": end + timedelta(hours=1)},
            )


async def coverage(db: AsyncSession) -> list[dict]:
    rows = await db.execute(
        text(
            "SELECT symbol, source, min(ts) AS first, max(ts) AS last, count(*) AS n, "
            "count(DISTINCT (ts AT TIME ZONE 'America/New_York')::date) AS days "
            "FROM bars GROUP BY symbol, source ORDER BY symbol"
        )
    )
    return [
        {"symbol": r.symbol, "source": r.source, "first": r.first, "last": r.last, "bars": r.n, "days": r.days}
        for r in rows
    ]


async def trading_days(db: AsyncSession, symbol: str, start: date, end: date) -> list[date]:
    a, b = range_bounds(start, end)
    rows = await db.execute(
        text(
            "SELECT DISTINCT (ts AT TIME ZONE 'America/New_York')::date AS d FROM bars "
            "WHERE symbol = :s AND ts >= :a AND ts < :b ORDER BY d"
        ),
        {"s": symbol, "a": a, "b": b},
    )
    return [r.d for r in rows]


# ----- implied volatility proxy ---------------------------------------------


async def upsert_iv(
    db: AsyncSession, index: str, rows: list[tuple[date, float | None, float | None]], overwrite: bool = True
) -> int:
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i : i + CHUNK]
        stmt = insert(IvDaily).values([dict(index=index, date=d, open=o, close=c) for d, o, c in chunk])
        if overwrite:
            stmt = stmt.on_conflict_do_update(
                index_elements=["index", "date"], set_={"open": stmt.excluded.open, "close": stmt.excluded.close}
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=["index", "date"])
        await db.execute(stmt)
    await db.commit()
    return len(rows)


class IvTable:
    """Vol-index level known at each session's open: that day's open print,
    falling back to the prior close. Never uses the same day's close."""

    def __init__(self) -> None:
        self.levels: dict[str, dict[date, float]] = defaultdict(dict)

    def __call__(self, index: str, day: date) -> float | None:
        table = self.levels.get(index)
        if not table:
            return None
        if day in table:
            return table[day]
        prior = [d for d in table if d <= day]
        return table[max(prior)] if prior else None

    @classmethod
    async def load(cls, db: AsyncSession, start: date, end: date) -> IvTable:
        out = cls()
        rows = await db.execute(
            select(IvDaily)
            .where(IvDaily.date >= start - timedelta(days=10), IvDaily.date <= end)
            .order_by(IvDaily.index, IvDaily.date)
        )
        prev_close: dict[str, float | None] = {}
        for r in rows.scalars():
            level = r.open or prev_close.get(r.index)
            if level:
                out.levels[r.index][r.date] = level
            prev_close[r.index] = r.close
        return out


# ----- options ----------------------------------------------------------------


async def upsert_option_contracts(db: AsyncSession, specs: list) -> None:
    if not specs:
        return
    stmt = insert(OptionContract).values(
        [dict(symbol=s.symbol, underlying=s.underlying, expiry=s.expiry, strike=s.strike, right=s.right) for s in specs]
    )
    await db.execute(stmt.on_conflict_do_nothing(index_elements=["symbol"]))
    await db.commit()


async def upsert_option_bars(db: AsyncSession, rows: list[tuple[str, Bar]]) -> int:
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i : i + CHUNK]
        stmt = insert(OptionBarRow).values(
            [
                dict(symbol=s, ts=b.ts, open=b.open, high=b.high, low=b.low, close=b.close,
                     volume=b.volume, vwap=b.vwap)
                for s, b in chunk
            ]
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "ts"],
            set_={c: stmt.excluded[c] for c in ("open", "high", "low", "close", "volume", "vwap")},
        )
        await db.execute(stmt)
    await db.commit()
    return len(rows)


class RealOptionBars:
    """Real option bars for one trading day, indexed for "latest bar at or
    before t" lookups. Bars more than 15 minutes old count as missing."""

    def __init__(self) -> None:
        self.day: date | None = None
        self._times: dict[str, list[datetime]] = {}
        self._bars: dict[str, list[Bar]] = {}

    def __call__(self, symbol: str, at: datetime) -> Bar | None:
        times = self._times.get(symbol)
        if not times:
            return None
        i = bisect.bisect_right(times, at) - 1
        if i < 0:
            return None
        bar = self._bars[symbol][i]
        return bar if at - bar.ts <= STALE_OPTION_BAR else None

    @property
    def contracts(self) -> int:
        return len(self._bars)

    async def load_day(self, db: AsyncSession, underlying: str, day: date) -> None:
        if self.day == day:
            return
        a, b = day_bounds(day)
        rows = await db.execute(
            select(OptionBarRow)
            .join(OptionContract, OptionContract.symbol == OptionBarRow.symbol)
            .where(OptionContract.underlying == underlying, OptionBarRow.ts >= a, OptionBarRow.ts < b)
            .order_by(OptionBarRow.symbol, OptionBarRow.ts)
        )
        times: dict[str, list[datetime]] = defaultdict(list)
        bars: dict[str, list[Bar]] = defaultdict(list)
        for r in rows.scalars():
            times[r.symbol].append(r.ts)
            bars[r.symbol].append(_to_bar(r))
        self._times, self._bars, self.day = dict(times), dict(bars), day
