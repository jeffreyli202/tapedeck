from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db import get_db
from app.models import JournalNote, TradeRow

router = APIRouter(prefix="/journal", tags=["journal"])
MAX_SCREENSHOT = 3_000_000


class NoteIn(BaseModel):
    title: str = Field("", max_length=200)
    body: str = ""
    tags: list[str] = []
    trade_id: int | None = None
    session_id: str | None = None
    run_id: str | None = None
    screenshot: str | None = Field(None, max_length=MAX_SCREENSHOT)


class NotePatch(BaseModel):
    title: str | None = Field(None, max_length=200)
    body: str | None = None
    tags: list[str] | None = None
    screenshot: str | None = Field(None, max_length=MAX_SCREENSHOT)


def _out(n: JournalNote, trade: TradeRow | None = None) -> dict:
    return {
        "id": n.id, "title": n.title, "body": n.body, "tags": n.tags or [], "trade_id": n.trade_id,
        "session_id": n.session_id, "run_id": n.run_id, "screenshot": n.screenshot,
        "created_at": n.created_at, "updated_at": n.updated_at,
        "trade": None if trade is None else {
            "symbol": trade.symbol, "direction": trade.direction, "qty": trade.qty, "pnl": trade.pnl,
            "entry_t": int(trade.entry_ts.timestamp()), "exit_t": int(trade.exit_ts.timestamp()),
            "entry_price": trade.entry_price, "exit_price": trade.exit_price,
        },
    }


async def _owned(db: AsyncSession, note_id: int, user: str) -> JournalNote:
    note = await db.get(JournalNote, note_id)
    if note is None or note.owner != user:
        raise HTTPException(404, "note not found")
    return note


@router.get("")
async def list_notes(
    session_id: str | None = None,
    run_id: str | None = None,
    tag: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(current_user),
) -> list[dict]:
    q = (
        select(JournalNote, TradeRow)
        .outerjoin(TradeRow, TradeRow.id == JournalNote.trade_id)
        .where(JournalNote.owner == user)
        .order_by(JournalNote.created_at.desc())
    )
    if session_id:
        q = q.where(JournalNote.session_id == session_id)
    if run_id:
        q = q.where(JournalNote.run_id == run_id)
    rows = (await db.execute(q)).all()
    notes = [_out(n, t) for n, t in rows]
    return [n for n in notes if tag in n["tags"]] if tag else notes


@router.post("")
async def create_note(body: NoteIn, db: AsyncSession = Depends(get_db), user: str = Depends(current_user)) -> dict:
    trade = None
    data = body.model_dump()
    if body.trade_id is not None:
        trade = await db.get(TradeRow, body.trade_id)
        if trade is None:
            raise HTTPException(404, "trade not found")
        data["session_id"] = data["session_id"] or trade.session_id
        data["run_id"] = data["run_id"] or trade.run_id
    note = JournalNote(owner=user, **data)
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return _out(note, trade)


@router.patch("/{note_id}")
async def update_note(
    note_id: int, body: NotePatch, db: AsyncSession = Depends(get_db), user: str = Depends(current_user)
) -> dict:
    note = await _owned(db, note_id, user)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(note, k, v)
    await db.commit()
    await db.refresh(note)
    trade = await db.get(TradeRow, note.trade_id) if note.trade_id else None
    return _out(note, trade)


@router.delete("/{note_id}")
async def delete_note(note_id: int, db: AsyncSession = Depends(get_db), user: str = Depends(current_user)) -> dict:
    await db.delete(await _owned(db, note_id, user))
    await db.commit()
    return {"ok": True}
