"""Runs a stored backtest request on the shared core and saves the results."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, date, datetime

from redis.asyncio import Redis
from sqlalchemy import delete

from app.config import settings
from app.core.fill_engine import FillEngine
from app.core.pricer import OptionPricer
from app.core.strategies import build_strategy
from app.core.strategy import Backtester
from app.data.store import IvTable, RealOptionBars, load_bars, range_bounds
from app.db import SessionLocal
from app.models import BacktestRun, EquityPointRow, TradeRow
from app.services.common import downsample, fill_config

log = logging.getLogger(__name__)


def channel(run_id: str) -> str:
    return f"backtest:{run_id}"


async def _publish(redis: Redis, run_id: str, event: dict) -> None:
    await redis.set(f"{channel(run_id)}:last", json.dumps(event), ex=3600)
    await redis.publish(channel(run_id), json.dumps(event))


async def execute_backtest(run_id: str, redis: Redis) -> dict:
    async with SessionLocal() as db:
        run = await db.get(BacktestRun, run_id)
        if run is None:
            raise ValueError(f"backtest {run_id} not found")
        run.status = "running"
        run.progress = 0
        await db.commit()
        try:
            strategy = build_strategy(run.strategy, run.params)
            a, b = range_bounds(run.start_date, run.end_date)
            bars = await load_bars(db, run.symbol, a, b)
            if not bars:
                raise ValueError(f"no {run.symbol} bars between {run.start_date} and {run.end_date}")
            iv = await IvTable.load(db, run.start_date, run.end_date)
        except Exception as exc:
            return await _fail(db, redis, run, exc)
        symbol = run.symbol
        starting_cash = run.starting_cash

    await _publish(redis, run_id, {"type": "progress", "status": "running", "progress": 0})
    real = RealOptionBars()
    pricer = OptionPricer(settings.risk_free_rate, iv, real)
    engine = FillEngine(starting_cash, fill_config())
    loop = asyncio.get_running_loop()

    async def load_real(day: date) -> None:
        async with SessionLocal() as db:
            await real.load_day(db, symbol, day)

    def on_new_day(day: date) -> None:
        if strategy.uses_options:
            asyncio.run_coroutine_threadsafe(load_real(day), loop).result()

    def progress(frac: float) -> None:
        event = {"type": "progress", "status": "running", "progress": frac}
        asyncio.run_coroutine_threadsafe(_publish(redis, run_id, event), loop)

    backtester = Backtester(strategy, symbol, bars, engine, pricer, progress, on_new_day)
    try:
        result = await asyncio.to_thread(backtester.run)
    except Exception as exc:
        async with SessionLocal() as db:
            run = await db.get(BacktestRun, run_id)
            return await _fail(db, redis, run, exc)

    async with SessionLocal() as db:
        await db.execute(delete(TradeRow).where(TradeRow.run_id == run_id))
        await db.execute(delete(EquityPointRow).where(EquityPointRow.run_id == run_id))
        db.add_all(
            TradeRow(
                run_id=run_id, symbol=t.symbol, direction=t.direction, qty=t.qty, entry_ts=t.entry_ts,
                exit_ts=t.exit_ts, entry_price=t.entry_price, exit_price=t.exit_price, pnl=t.pnl,
                commission=t.commission,
            )
            for t in result.trades
        )
        db.add_all(
            EquityPointRow(run_id=run_id, ts=p.ts, equity=p.equity, exposure=p.exposure)
            for p in downsample(result.equity)
        )
        run = await db.get(BacktestRun, run_id)
        run.status = "done"
        run.progress = 1
        run.metrics = result.metrics
        run.finished_at = datetime.now(UTC)
        await db.commit()
    await _publish(redis, run_id, {"type": "done", "status": "done", "progress": 1, "metrics": result.metrics})
    return result.metrics


async def _fail(db, redis: Redis, run: BacktestRun, exc: Exception) -> dict:
    log.error("backtest %s failed", run.id, exc_info=exc)
    run.status = "failed"
    run.error = str(exc)
    run.finished_at = datetime.now(UTC)
    await db.commit()
    await _publish(redis, run.id, {"type": "failed", "status": "failed", "error": str(exc)})
    return {"error": str(exc)}
