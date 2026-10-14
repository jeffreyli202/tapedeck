from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.config import settings
from app.core.strategies import STRATEGIES
from app.db import get_db
from app.deps import get_arq, owned_run
from app.models import BacktestRun

router = APIRouter(tags=["backtests"])


class BacktestIn(BaseModel):
    strategy: str
    symbol: Literal["SPY", "QQQ"]
    start_date: date
    end_date: date
    starting_cash: float | None = Field(None, gt=0)
    params: dict = {}


def _run_out(r: BacktestRun) -> dict:
    return {
        "id": r.id, "strategy": r.strategy, "symbol": r.symbol, "start_date": r.start_date,
        "end_date": r.end_date, "starting_cash": r.starting_cash, "params": r.params, "status": r.status,
        "progress": r.progress, "error": r.error, "metrics": r.metrics, "created_at": r.created_at,
        "finished_at": r.finished_at,
    }


@router.get("/strategies")
async def strategies() -> list[dict]:
    return [cls.schema() for cls in STRATEGIES.values()]


@router.post("/backtests")
async def create_backtest(
    body: BacktestIn,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(current_user),
    arq: ArqRedis = Depends(get_arq),
) -> dict:
    cls = STRATEGIES.get(body.strategy)
    if cls is None:
        raise HTTPException(400, f"unknown strategy {body.strategy}")
    if body.end_date < body.start_date:
        raise HTTPException(400, "end_date is before start_date")
    try:
        params = cls.Params(**body.params).model_dump()
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False)) from exc
    run = BacktestRun(
        id=uuid.uuid4().hex[:12], owner=user, strategy=body.strategy, symbol=body.symbol,
        start_date=body.start_date, end_date=body.end_date,
        starting_cash=body.starting_cash or settings.starting_cash, params=params, status="queued",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    await arq.enqueue_job("run_backtest", run.id, _job_id=f"backtest:{run.id}")
    return _run_out(run)


@router.get("/backtests")
async def list_backtests(db: AsyncSession = Depends(get_db), user: str = Depends(current_user)) -> list[dict]:
    rows = await db.execute(
        select(BacktestRun).where(BacktestRun.owner == user).order_by(BacktestRun.created_at.desc())
    )
    return [_run_out(r) for r in rows.scalars()]


@router.get("/backtests/{run_id}")
async def get_backtest(run_id: str, db: AsyncSession = Depends(get_db), user: str = Depends(current_user)) -> dict:
    return _run_out(await owned_run(db, run_id, user))


@router.delete("/backtests/{run_id}")
async def delete_backtest(run_id: str, db: AsyncSession = Depends(get_db), user: str = Depends(current_user)) -> dict:
    await db.delete(await owned_run(db, run_id, user))
    await db.commit()
    return {"ok": True}
