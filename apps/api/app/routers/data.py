from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from arq.connections import ArqRedis
from arq.jobs import Job
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.config import settings
from app.data.store import TIMEFRAMES, coverage, load_bars, trading_days
from app.db import get_db
from app.deps import get_arq, get_redis

router = APIRouter(prefix="/data", tags=["data"])


class JobIn(BaseModel):
    kind: Literal["bars", "iv", "options", "synthetic"]
    symbol: Literal["SPY", "QQQ"] = "SPY"
    start: date | None = None
    end: date | None = None
    day: date | None = None
    days: int = 20


@router.get("/status")
async def status(db: AsyncSession = Depends(get_db), _: str = Depends(current_user)) -> dict:
    iv = await db.execute(
        text('SELECT index, min(date) AS first, max(date) AS last, count(*) AS n FROM iv_daily GROUP BY index')
    )
    opts = await db.execute(
        text(
            "SELECT c.underlying, count(DISTINCT b.symbol) AS contracts, count(*) AS n, min(b.ts) AS first, "
            "max(b.ts) AS last FROM option_bars b JOIN option_contracts c ON c.symbol = b.symbol GROUP BY c.underlying"
        )
    )
    return {
        "alpaca_configured": bool(settings.alpaca_api_key and settings.alpaca_secret_key),
        "bars": await coverage(db),
        "iv": [{"index": r.index, "first": r.first, "last": r.last, "days": r.n} for r in iv],
        "options": [
            {"underlying": r.underlying, "contracts": r.contracts, "bars": r.n, "first": r.first, "last": r.last}
            for r in opts
        ],
    }


@router.get("/days")
async def days(
    symbol: str, start: date | None = None, end: date | None = None,
    db: AsyncSession = Depends(get_db), _: str = Depends(current_user),
) -> list[date]:
    return await trading_days(db, symbol, start or date(2000, 1, 1), end or date.today())


@router.get("/bars")
async def bars(
    symbol: str, start: datetime, end: datetime, timeframe: str = "1m",
    db: AsyncSession = Depends(get_db), _: str = Depends(current_user),
) -> list[dict]:
    if timeframe not in TIMEFRAMES:
        raise HTTPException(400, f"timeframe must be one of {list(TIMEFRAMES)}")
    return [b.to_dict() for b in await load_bars(db, symbol, start, end, timeframe)]


@router.post("/jobs")
async def enqueue(body: JobIn, arq: ArqRedis = Depends(get_arq), _: str = Depends(current_user)) -> dict:
    if body.kind in ("bars", "options") and not (settings.alpaca_api_key and settings.alpaca_secret_key):
        raise HTTPException(400, "Alpaca keys are not configured; add them to .env or use synthetic data")
    if body.kind == "bars":
        if not body.start or not body.end:
            raise HTTPException(400, "start and end are required")
        job = await arq.enqueue_job("ingest_bars", body.symbol, body.start.isoformat(), body.end.isoformat())
    elif body.kind == "iv":
        job = await arq.enqueue_job("ingest_iv")
    elif body.kind == "options":
        if not body.day:
            raise HTTPException(400, "day is required")
        job = await arq.enqueue_job("ingest_options", body.symbol, body.day.isoformat())
    else:
        job = await arq.enqueue_job("seed_synthetic", max(1, min(body.days, 250)))
    if job is None:
        raise HTTPException(409, "an identical job is already queued")
    return {"job_id": job.job_id}


@router.get("/jobs/{job_id}")
async def job_status(
    job_id: str, arq: ArqRedis = Depends(get_arq), redis: Redis = Depends(get_redis), _: str = Depends(current_user)
) -> dict:
    job = Job(job_id, arq)
    status = await job.status()
    progress = await redis.hgetall(f"job:{job_id}")
    out = {"job_id": job_id, "status": status.value, **progress}
    info = await job.result_info()
    if info is not None:
        out["success"] = info.success
        out["result"] = info.result if info.success else str(info.result)
    return out
