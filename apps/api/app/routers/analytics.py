from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.core import metrics as m
from app.db import get_db
from app.deps import owned_run, owned_session
from app.models import EquityPointRow, JournalNote, TradeRow

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _trade_out(t: TradeRow, noted: set[int]) -> dict:
    return {
        "id": t.id, "symbol": t.symbol, "direction": t.direction, "qty": t.qty,
        "entry_t": int(t.entry_ts.timestamp()), "exit_t": int(t.exit_ts.timestamp()),
        "entry_price": t.entry_price, "exit_price": t.exit_price, "pnl": t.pnl,
        "commission": t.commission, "has_note": t.id in noted,
    }


@router.get("")
async def analytics(
    run_id: str | None = None,
    session_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(current_user),
) -> dict:
    if bool(run_id) == bool(session_id):
        raise HTTPException(400, "pass exactly one of run_id or session_id")
    if run_id:
        source = await owned_run(db, run_id, user)
        col_t, col_e, key = TradeRow.run_id, EquityPointRow.run_id, run_id
    else:
        source = await owned_session(db, session_id, user)
        col_t, col_e, key = TradeRow.session_id, EquityPointRow.session_id, session_id

    trades = (await db.execute(select(TradeRow).where(col_t == key).order_by(TradeRow.exit_ts))).scalars().all()
    eq_rows = (
        await db.execute(select(EquityPointRow).where(col_e == key).order_by(EquityPointRow.ts))
    ).scalars().all()
    noted = set(
        (
            await db.execute(
                select(JournalNote.trade_id).where(JournalNote.trade_id.in_([t.id for t in trades]))
            )
        ).scalars()
    )

    points = [m.EquityPoint(e.ts, e.equity, e.exposure) for e in eq_rows]
    records = [m.TradeRecord(t.pnl, t.entry_ts, t.exit_ts, t.direction) for t in trades]
    stats = m.compute_metrics(points, records, source.starting_cash)
    if run_id and source.metrics:
        stats = source.metrics

    return {
        "metrics": stats,
        "equity": [{"t": int(p.ts.timestamp()), "equity": p.equity} for p in points],
        "drawdown": m.drawdown_series(points),
        "histogram": m.histogram(records),
        "by_time_of_day": m.by_time_of_day(records),
        "by_weekday": m.by_weekday(records),
        "heatmap": m.heatmap(records),
        "trades": [_trade_out(t, noted) for t in trades],
    }
