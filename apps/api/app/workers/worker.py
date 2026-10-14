"""arq worker: `arq app.workers.worker.WorkerSettings`."""

from __future__ import annotations

import logging
from datetime import date

from arq.connections import RedisSettings
from redis.asyncio import Redis

from app.config import settings
from app.services import backtests, ingest

logging.basicConfig(level=logging.INFO)


async def startup(ctx: dict) -> None:
    ctx["r"] = Redis.from_url(settings.redis_url, decode_responses=True)


async def shutdown(ctx: dict) -> None:
    await ctx["r"].aclose()


async def ingest_bars(ctx: dict, symbol: str, start: str, end: str) -> dict:
    return await ingest.ingest_stock_bars(
        symbol, date.fromisoformat(start), date.fromisoformat(end), ctx["r"], ctx["job_id"]
    )


async def ingest_iv(ctx: dict) -> dict:
    return await ingest.ingest_vol_indices(ctx["r"], ctx["job_id"])


async def ingest_options(ctx: dict, underlying: str, day: str, strikes: int = 10) -> dict:
    return await ingest.ingest_option_day(underlying, date.fromisoformat(day), strikes, ctx["r"], ctx["job_id"])


async def seed_synthetic(ctx: dict, days: int = 20) -> dict:
    return await ingest.seed_synthetic(days, redis=ctx["r"], job_id=ctx["job_id"])


async def run_backtest(ctx: dict, run_id: str) -> dict:
    return await backtests.execute_backtest(run_id, ctx["r"])


class WorkerSettings:
    functions = [ingest_bars, ingest_iv, ingest_options, seed_synthetic, run_backtest]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    job_timeout = 3 * 3600
    max_jobs = 4
