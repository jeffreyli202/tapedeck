"""Ingestion jobs: Alpaca stock and option bars, vol-index levels, synthetic seed data."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from redis.asyncio import Redis

from app.data import alpaca, iv, synthetic
from app.data.store import (
    day_bounds,
    load_bars,
    range_bounds,
    refresh_aggregates,
    upsert_bars,
    upsert_iv,
    upsert_option_bars,
    upsert_option_contracts,
)
from app.db import SessionLocal

CHUNK_DAYS = 30


async def _progress(redis: Redis | None, job_id: str | None, frac: float, message: str) -> None:
    if redis and job_id:
        await redis.hset(f"job:{job_id}", mapping={"progress": f"{frac:.3f}", "message": message})
        await redis.expire(f"job:{job_id}", 86400)


async def ingest_stock_bars(
    symbol: str, start: date, end: date, redis: Redis | None = None, job_id: str | None = None
) -> dict:
    total = 0
    chunks = []
    d = start
    while d <= end:
        chunks.append((d, min(end, d + timedelta(days=CHUNK_DAYS - 1))))
        d += timedelta(days=CHUNK_DAYS)
    for i, (a, b) in enumerate(chunks):
        lo, hi = range_bounds(a, b)
        bars = await asyncio.to_thread(alpaca.fetch_stock_bars, symbol, lo, hi)
        async with SessionLocal() as db:
            total += await upsert_bars(db, symbol, bars, "alpaca")
        await _progress(redis, job_id, (i + 1) / len(chunks), f"{symbol} {a}..{b}: {total} bars")
    if total:
        await refresh_aggregates(*range_bounds(start, end))
    return {"symbol": symbol, "bars": total}


async def ingest_vol_indices(redis: Redis | None = None, job_id: str | None = None) -> dict:
    out = {}
    for index in ("VIX", "VXN"):
        rows, source = await iv.fetch_index(index)
        async with SessionLocal() as db:
            out[index] = {"rows": await upsert_iv(db, index, rows), "source": source}
        await _progress(redis, job_id, 0.5 if index == "VIX" else 1.0, f"{index}: {len(rows)} days from {source}")
    return out


async def ingest_option_day(
    underlying: str, day: date, n_strikes: int = 10, redis: Redis | None = None, job_id: str | None = None
) -> dict:
    lo, hi = day_bounds(day)
    async with SessionLocal() as db:
        bars = await load_bars(db, underlying, lo, hi)
    if not bars:
        raise ValueError(f"ingest {underlying} stock bars for {day} first")
    specs = alpaca.contracts_for_day(underlying, day, bars[0].open, n_strikes)
    rows = await asyncio.to_thread(alpaca.fetch_option_bars, specs, lo, hi)
    traded = {s for s, _ in rows}
    async with SessionLocal() as db:
        await upsert_option_contracts(db, [s for s in specs if s.symbol in traded])
        n = await upsert_option_bars(db, rows)
    await _progress(redis, job_id, 1.0, f"{len(traded)} contracts, {n} bars")
    return {"underlying": underlying, "day": day.isoformat(), "contracts": len(traded), "bars": n}


async def seed_synthetic(days: int = 20, end: date | None = None, redis: Redis | None = None, job_id: str | None = None) -> dict:
    end = end or date.today() - timedelta(days=1)
    trading_days = synthetic.weekdays_back(end, days)
    out = {}
    for i, symbol in enumerate(("SPY", "QQQ")):
        bars, iv_rows = synthetic.generate(symbol, trading_days)
        async with SessionLocal() as db:
            out[symbol] = await upsert_bars(db, symbol, bars, "synthetic", overwrite=False)
            await upsert_iv(db, synthetic.VOL_INDEX[symbol], iv_rows, overwrite=False)
        await _progress(redis, job_id, (i + 1) / 2, f"{symbol}: {len(bars)} synthetic bars")
    await refresh_aggregates(*range_bounds(trading_days[0], trading_days[-1]))
    return {"days": [trading_days[0].isoformat(), trading_days[-1].isoformat()], **out}
