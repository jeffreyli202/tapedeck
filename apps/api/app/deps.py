from arq.connections import ArqRedis
from fastapi import HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BacktestRun, ReplaySession
from app.services.replay import ReplayManager


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


def get_arq(request: Request) -> ArqRedis:
    return request.app.state.arq


def get_replay(request: Request) -> ReplayManager:
    return request.app.state.replay


async def owned_session(db: AsyncSession, session_id: str, user: str) -> ReplaySession:
    row = await db.get(ReplaySession, session_id)
    if row is None or row.owner != user:
        raise HTTPException(404, "session not found")
    return row


async def owned_run(db: AsyncSession, run_id: str, user: str) -> BacktestRun:
    row = await db.get(BacktestRun, run_id)
    if row is None or row.owner != user:
        raise HTTPException(404, "backtest not found")
    return row
