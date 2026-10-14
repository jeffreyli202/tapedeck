"""WebSockets: replay streams (bars, fills, P&L ticks + transport commands) and
backtest progress. Both relay Redis pub/sub channels."""

from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.auth import decode_token
from app.db import SessionLocal
from app.models import BacktestRun, ReplaySession
from app.services import backtests
from app.services.replay import ReplayError, channel

router = APIRouter()


async def _relay(ws: WebSocket, chan: str, inbound=None, on_subscribed=None) -> None:
    pubsub = ws.app.state.redis.pubsub()
    await pubsub.subscribe(chan)
    if on_subscribed:
        await on_subscribed()

    async def outbound() -> None:
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                await ws.send_text(msg["data"])

    tasks = [asyncio.create_task(outbound())]
    if inbound:
        tasks.append(asyncio.create_task(inbound()))
    else:
        tasks.append(asyncio.create_task(_drain(ws)))
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            t.cancel()
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(chan)
            await pubsub.aclose()


async def _drain(ws: WebSocket) -> None:
    with contextlib.suppress(WebSocketDisconnect):
        while True:
            await ws.receive_text()


@router.websocket("/ws/replay/{session_id}")
async def replay_ws(ws: WebSocket, session_id: str, token: str | None = None) -> None:
    user = decode_token(token)
    async with SessionLocal() as db:
        row = await db.get(ReplaySession, session_id)
    if user is None or row is None or row.owner != user:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await ws.accept()
    replay = ws.app.state.replay

    async def inbound() -> None:
        with contextlib.suppress(WebSocketDisconnect):
            while True:
                msg = await ws.receive_json()
                try:
                    await replay.command(session_id, msg.get("action"), msg.get("value"))
                except (ReplayError, ValueError, TypeError) as exc:
                    await ws.send_json({"type": "error", "message": str(exc)})

    async def send_snapshot() -> None:
        try:
            await ws.send_json({"type": "snapshot", **(await replay.snapshot(session_id))})
        except ReplayError as exc:
            await ws.send_json({"type": "error", "message": str(exc)})

    # The snapshot is taken after subscribing so no tick falls in between; the
    # client drops ticks at or before the snapshot's index.
    await _relay(ws, channel(session_id), inbound, send_snapshot)


@router.websocket("/ws/backtests/{run_id}")
async def backtest_ws(ws: WebSocket, run_id: str, token: str | None = None) -> None:
    user = decode_token(token)
    async with SessionLocal() as db:
        run = await db.get(BacktestRun, run_id)
    if user is None or run is None or run.owner != user:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await ws.accept()
    last = await ws.app.state.redis.get(f"{backtests.channel(run_id)}:last")
    await ws.send_json(
        json.loads(last) if last else {"type": "progress", "status": run.status, "progress": run.progress}
    )
    await _relay(ws, backtests.channel(run_id))
