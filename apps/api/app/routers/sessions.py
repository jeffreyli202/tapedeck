from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.config import settings
from app.data.store import trading_days
from app.db import get_db
from app.deps import get_replay, owned_session
from app.models import Account, FillRow, ReplaySession
from app.services.replay import ReplayManager, fill_dict

router = APIRouter(prefix="/sessions", tags=["replay"])


class SessionCreate(BaseModel):
    symbol: Literal["SPY", "QQQ"]
    start_date: date
    end_date: date | None = None
    starting_cash: float | None = Field(None, gt=0)
    speed: float = Field(10, ge=1, le=60)


class Control(BaseModel):
    action: Literal["play", "pause", "speed", "step", "seek", "next_day"]
    value: float | int | None = None


class OrderIn(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    qty: int = Field(gt=0)
    type: Literal["market", "limit", "stop"] = "market"
    limit_price: float | None = Field(None, gt=0)
    stop_price: float | None = Field(None, gt=0)
    take_profit: float | None = Field(None, gt=0)
    stop_loss: float | None = Field(None, gt=0)
    tag: str | None = None


def _session_out(row: ReplaySession, equity: float | None = None) -> dict:
    return {
        "id": row.id,
        "symbol": row.symbol,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "status": row.status,
        "speed": row.speed,
        "cursor_ts": int(row.cursor_ts.timestamp()) if row.cursor_ts else None,
        "starting_cash": row.starting_cash,
        "equity": equity,
        "created_at": row.created_at,
    }


@router.post("")
async def create_session(
    body: SessionCreate, db: AsyncSession = Depends(get_db), user: str = Depends(current_user)
) -> dict:
    end = body.end_date or body.start_date
    if end < body.start_date:
        raise HTTPException(400, "end_date is before start_date")
    days = await trading_days(db, body.symbol, body.start_date, end)
    if not days:
        raise HTTPException(400, f"no {body.symbol} data between {body.start_date} and {end}; ingest it first")
    cash = body.starting_cash or settings.starting_cash
    account = Account(owner=user, name=f"{body.symbol} replay {body.start_date}", starting_cash=cash)
    db.add(account)
    await db.flush()
    row = ReplaySession(
        id=uuid.uuid4().hex[:12], owner=user, account_id=account.id, symbol=body.symbol,
        start_date=days[0], end_date=days[-1], speed=body.speed, status="paused", starting_cash=cash,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _session_out(row, cash)


@router.get("")
async def list_sessions(db: AsyncSession = Depends(get_db), user: str = Depends(current_user)) -> list[dict]:
    rows = (
        await db.execute(
            select(ReplaySession).where(ReplaySession.owner == user).order_by(ReplaySession.created_at.desc())
        )
    ).scalars().all()
    equity = {
        r.session_id: r.equity
        for r in await db.execute(
            text(
                "SELECT DISTINCT ON (session_id) session_id, equity FROM equity_points "
                "WHERE session_id = ANY(:ids) ORDER BY session_id, ts DESC"
            ),
            {"ids": [r.id for r in rows]},
        )
    }
    return [_session_out(r, equity.get(r.id, r.starting_cash)) for r in rows]


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(current_user),
    replay: ReplayManager = Depends(get_replay),
) -> dict:
    await owned_session(db, session_id, user)
    return await replay.snapshot(session_id)


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(current_user),
    replay: ReplayManager = Depends(get_replay),
) -> dict:
    row = await owned_session(db, session_id, user)
    await replay.drop(session_id)
    await db.delete(await db.get(Account, row.account_id))
    await db.commit()
    return {"ok": True}


@router.post("/{session_id}/control")
async def control(
    session_id: str,
    body: Control,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(current_user),
    replay: ReplayManager = Depends(get_replay),
) -> dict:
    await owned_session(db, session_id, user)
    return await replay.command(session_id, body.action, body.value)


@router.post("/{session_id}/orders")
async def place_order(
    session_id: str,
    body: OrderIn,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(current_user),
    replay: ReplayManager = Depends(get_replay),
) -> dict:
    await owned_session(db, session_id, user)
    return await replay.submit_order(session_id, body.model_dump())


@router.delete("/{session_id}/orders/{order_id}")
async def cancel_order(
    session_id: str,
    order_id: str,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(current_user),
    replay: ReplayManager = Depends(get_replay),
) -> dict:
    await owned_session(db, session_id, user)
    return await replay.cancel_order(session_id, order_id)


@router.post("/{session_id}/flatten")
async def flatten(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(current_user),
    replay: ReplayManager = Depends(get_replay),
) -> dict:
    await owned_session(db, session_id, user)
    await replay.flatten(session_id)
    return {"ok": True}


@router.get("/{session_id}/chain")
async def option_chain(
    session_id: str,
    expiry: str | None = None,
    strikes: int = 10,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(current_user),
    replay: ReplayManager = Depends(get_replay),
) -> dict:
    await owned_session(db, session_id, user)
    return await replay.chain(session_id, expiry, min(max(strikes, 2), 30))


@router.get("/{session_id}/fills")
async def fills(session_id: str, db: AsyncSession = Depends(get_db), user: str = Depends(current_user)) -> list:
    await owned_session(db, session_id, user)
    rows = (await db.execute(select(FillRow).where(FillRow.session_id == session_id).order_by(FillRow.ts))).scalars()
    return [fill_dict(f) for f in rows]
