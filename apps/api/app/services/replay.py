"""Server-side replay sessions.

The clock state (cursor, speed, status) and the paper account live in Redis so
they survive reconnects; every revealed bar is published on a Redis channel
that WebSocket clients subscribe to. The client only sends commands and
orders; it never decides what time it is.

Runtimes are held in this API process, so run a single API worker.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import delete, select

from app.config import settings
from app.core.clock import ClockStatus, ReplayClock
from app.core.fill_engine import Fill, FillEngine, Order, OrderStatus, OrderType, Side
from app.core.occ import is_option, parse_occ
from app.core.pricer import OptionPricer, list_expiries
from app.core.types import et
from app.data.store import IvTable, RealOptionBars, load_bars, range_bounds
from app.db import SessionLocal
from app.models import EquityPointRow, FillRow, OrderRow, PositionRow, ReplaySession, TradeRow
from app.services.common import fill_config

log = logging.getLogger(__name__)


def channel(session_id: str) -> str:
    return f"replay:{session_id}"


def state_key(session_id: str) -> str:
    return f"replay:{session_id}:state"


def engine_key(session_id: str) -> str:
    return f"replay:{session_id}:engine"


def _epoch(ts: datetime | None) -> int | None:
    return int(ts.timestamp()) if ts else None


def order_dict(o: Order) -> dict:
    return {
        "id": o.id, "symbol": o.symbol, "asset_class": o.asset_class, "side": o.side.value,
        "qty": o.qty, "type": o.type.value, "limit_price": o.limit_price, "stop_price": o.stop_price,
        "take_profit": o.take_profit, "stop_loss": o.stop_loss, "status": o.status.value,
        "parent_id": o.parent_id, "tag": o.tag, "reason": o.reason,
        "created_ts": _epoch(o.created_ts), "filled_ts": _epoch(o.filled_ts), "fill_price": o.fill_price,
    }


def fill_dict(f: Fill | FillRow) -> dict:
    side = f.side.value if isinstance(f.side, Side) else f.side
    return {
        "order_id": f.order_id, "symbol": f.symbol, "side": side, "qty": f.qty, "price": f.price,
        "commission": f.commission, "t": _epoch(f.ts), "price_source": f.price_source,
    }


class ReplayError(Exception):
    pass


@dataclass
class Runtime:
    id: str
    owner: str
    symbol: str
    starting_cash: float
    clock: ReplayClock
    engine: FillEngine
    pricer: OptionPricer
    real: RealOptionBars
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    task: asyncio.Task | None = None
    saved_fills: int = 0
    saved_trades: int = 0
    saved_orders: dict[str, str] = field(default_factory=dict)
    pending_equity: list[tuple[datetime, float, float]] = field(default_factory=list)

    @property
    def has_traded(self) -> bool:
        return any(o.status == OrderStatus.FILLED for o in self.engine.orders.values())

    def orders(self) -> list[dict]:
        ordered = sorted(
            self.engine.orders.values(),
            key=lambda o: o.created_ts.timestamp() if o.created_ts else 0,
            reverse=True,
        )
        return [order_dict(o) for o in ordered[:200]]


class ReplayManager:
    def __init__(self, redis: Redis):
        self.redis = redis
        self.runtimes: dict[str, Runtime] = {}
        self._loading = asyncio.Lock()

    # ----- lifecycle ---------------------------------------------------

    async def get(self, session_id: str) -> Runtime:
        if session_id in self.runtimes:
            return self.runtimes[session_id]
        async with self._loading:
            if session_id not in self.runtimes:
                self.runtimes[session_id] = await self._load(session_id)
        return self.runtimes[session_id]

    async def _load(self, session_id: str) -> Runtime:
        async with SessionLocal() as db:
            row = await db.get(ReplaySession, session_id)
            if row is None:
                raise ReplayError("session not found")
            a, b = range_bounds(row.start_date, row.end_date)
            bars = await load_bars(db, row.symbol, a, b)
            if not bars:
                raise ReplayError(f"no {row.symbol} bars between {row.start_date} and {row.end_date}")
            iv = await IvTable.load(db, row.start_date, row.end_date)

            state = await self.redis.hgetall(state_key(session_id))
            raw_engine = await self.redis.get(engine_key(session_id))
            if raw_engine:
                engine = FillEngine.from_dict(json.loads(raw_engine))
            elif row.engine_state:
                engine = FillEngine.from_dict(row.engine_state)
            else:
                engine = FillEngine(row.starting_cash, fill_config())

            clock = ReplayClock(bars, speed=float(state.get("speed", row.speed)))
            if "index" in state:
                clock.index = min(int(state["index"]), len(bars) - 1)
            elif row.cursor_ts:
                clock.index = clock.index_at(row.cursor_ts)
            if clock.at_end:
                clock.status = ClockStatus.FINISHED
            engine.last_prices.setdefault(row.symbol, clock.cursor.close)

            real = RealOptionBars()
            await real.load_day(db, row.symbol, et(clock.cursor.ts).date())
            rt = Runtime(
                id=session_id,
                owner=row.owner,
                symbol=row.symbol,
                starting_cash=row.starting_cash,
                clock=clock,
                engine=engine,
                pricer=OptionPricer(settings.risk_free_rate, iv, real),
                real=real,
                saved_trades=len(engine.closed_trades),
                saved_orders={o.id: o.status.value for o in engine.orders.values()},
            )
        await self._save_redis(rt)
        return rt

    async def shutdown(self) -> None:
        for rt in list(self.runtimes.values()):
            if rt.clock.status == ClockStatus.PLAYING:
                rt.clock.status = ClockStatus.PAUSED
            if rt.task:
                rt.task.cancel()
            async with rt.lock:
                await self._flush(rt, durable=True)

    async def drop(self, session_id: str) -> None:
        rt = self.runtimes.pop(session_id, None)
        if rt and rt.task:
            rt.task.cancel()
        await self.redis.delete(state_key(session_id), engine_key(session_id))

    # ----- transport ---------------------------------------------------

    async def command(self, session_id: str, action: str, value=None) -> dict:
        rt = await self.get(session_id)
        if action == "play":
            if rt.clock.status != ClockStatus.FINISHED:
                rt.clock.status = ClockStatus.PLAYING
                if rt.task is None or rt.task.done():
                    rt.task = asyncio.create_task(self._run(rt))
        elif action == "pause":
            if rt.clock.status == ClockStatus.PLAYING:
                rt.clock.status = ClockStatus.PAUSED
            async with rt.lock:
                await self._flush(rt, durable=True)
        elif action == "speed":
            rt.clock.set_speed(float(value))
        elif action == "step":
            async with rt.lock:
                for _ in range(max(1, int(value or 1))):
                    if rt.clock.at_end:
                        break
                    await self._advance(rt)
                await self._flush(rt, durable=rt.clock.status == ClockStatus.FINISHED)
            return rt.clock.state()
        elif action == "seek":
            await self._seek(rt, datetime.fromtimestamp(int(value), tz=UTC))
            return rt.clock.state()
        elif action == "next_day":
            nxt = rt.clock.next_day_index()
            if nxt is None:
                raise ReplayError("already on the last day of this session")
            await self._seek(rt, rt.clock.bars[nxt].ts)
            return rt.clock.state()
        else:
            raise ReplayError(f"unknown action {action!r}")
        await self._save_redis(rt)
        await self._publish(rt, {"type": "state", "state": rt.clock.state()})
        return rt.clock.state()

    async def _run(self, rt: Runtime) -> None:
        try:
            while rt.clock.status == ClockStatus.PLAYING:
                await asyncio.sleep(rt.clock.interval_seconds)
                async with rt.lock:
                    if rt.clock.status != ClockStatus.PLAYING:
                        break
                    await self._advance(rt)
                    await self._flush(rt, durable=rt.clock.status == ClockStatus.FINISHED)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("replay loop for %s crashed", rt.id)
            rt.clock.status = ClockStatus.PAUSED
            await self._publish(rt, {"type": "error", "message": "replay loop crashed; paused"})

    async def _seek(self, rt: Runtime, ts: datetime) -> None:
        async with rt.lock:
            target = rt.clock.index_at(ts)
            if target < rt.clock.index:
                if rt.has_traded:
                    raise ReplayError("can't rewind a session that has fills; start a new session instead")
                rt.engine.cancel_all(reason="rewound")
                rt.clock.index = target
                rt.clock.status = ClockStatus.PAUSED
                rt.engine.last_prices[rt.symbol] = rt.clock.cursor.close
                async with SessionLocal() as db:
                    await db.execute(
                        delete(EquityPointRow).where(
                            EquityPointRow.session_id == rt.id, EquityPointRow.ts > rt.clock.cursor.end
                        )
                    )
                    await db.commit()
            else:
                # Fast-forward bar by bar so resting orders still fill on the way.
                while rt.clock.index < target:
                    await self._advance(rt, publish=False)
                if rt.clock.status == ClockStatus.PLAYING and rt.clock.at_end:
                    rt.clock.status = ClockStatus.FINISHED
            await self._flush(rt, durable=True)
        await self._publish(rt, {"type": "reset", **(await self.snapshot(rt.id))})

    # ----- the tick ----------------------------------------------------

    async def _advance(self, rt: Runtime, publish: bool = True) -> None:
        bar = rt.clock.advance()
        if bar is None:
            await self._publish(rt, {"type": "state", "state": rt.clock.state()})
            return
        day = et(bar.ts).date()
        if rt.real.day != day:
            async with SessionLocal() as db:
                await rt.real.load_day(db, rt.symbol, day)

        engine = rt.engine
        fills = engine.on_bar(rt.symbol, bar)
        option_symbols = {o.symbol for o in engine.open_orders() if is_option(o.symbol)}
        option_symbols |= {p.symbol for p in engine.open_positions() if is_option(p.symbol)}
        for sym in option_symbols:
            spec = parse_occ(sym)
            if spec and spec.expiry >= day:
                obar, source = rt.pricer.option_bar(sym, bar)
                fills += engine.on_bar(sym, obar, source)

        if rt.clock.is_day_end():
            for o in engine.open_orders():
                if o.parent_id is None:
                    engine.cancel(o.id, "day order expired")
            fills += engine.settle_expiries(day, bar.end)

        rt.pending_equity.append((bar.end, engine.equity(), engine.gross_exposure()))
        if publish:
            await self._publish(
                rt,
                {
                    "type": "tick",
                    "bar": bar.to_dict(),
                    "state": rt.clock.state(),
                    "account": engine.summary(),
                    "fills": [fill_dict(f) for f in fills],
                    "orders": rt.orders() if fills or any(
                        rt.saved_orders.get(o.id) != o.status.value for o in engine.orders.values()
                    ) else None,
                },
            )

    # ----- orders ------------------------------------------------------

    async def submit_order(self, session_id: str, req: dict) -> dict:
        rt = await self.get(session_id)
        async with rt.lock:
            symbol = req["symbol"].upper()
            cursor = rt.clock.cursor
            if is_option(symbol):
                spec = parse_occ(symbol)
                if spec.underlying != rt.symbol:
                    raise ReplayError(f"this session only trades {rt.symbol} and its options")
                if spec.expiry < et(cursor.ts).date():
                    raise ReplayError("contract already expired")
                quote = rt.pricer.quote(spec, cursor.close, cursor.end)
                rt.engine.last_prices[symbol] = quote.price
            elif symbol != rt.symbol:
                raise ReplayError(f"this session only trades {rt.symbol} and its options")
            if rt.clock.status == ClockStatus.FINISHED:
                raise ReplayError("session finished")
            order = Order(
                symbol=symbol,
                side=Side(req["side"]),
                qty=int(req["qty"]),
                type=OrderType(req.get("type", "market")),
                limit_price=req.get("limit_price"),
                stop_price=req.get("stop_price"),
                take_profit=req.get("take_profit"),
                stop_loss=req.get("stop_loss"),
                tag=req.get("tag"),
            )
            rt.engine.submit(order, cursor.ts)
            await self._flush(rt)
        await self._publish(rt, {"type": "orders", "orders": rt.orders(), "account": rt.engine.summary()})
        return order_dict(order)

    async def cancel_order(self, session_id: str, order_id: str) -> dict:
        rt = await self.get(session_id)
        async with rt.lock:
            order = rt.engine.cancel(order_id)
            if order is None:
                raise ReplayError("order not found")
            await self._flush(rt)
        await self._publish(rt, {"type": "orders", "orders": rt.orders()})
        return order_dict(order)

    async def flatten(self, session_id: str) -> None:
        rt = await self.get(session_id)
        async with rt.lock:
            rt.engine.cancel_all(reason="flatten")
            for p in rt.engine.open_positions():
                o = Order(symbol=p.symbol, side=Side.SELL if p.qty > 0 else Side.BUY, qty=abs(p.qty), tag="flatten")
                rt.engine.submit(o, rt.clock.cursor.ts)
            await self._flush(rt)
        await self._publish(rt, {"type": "orders", "orders": rt.orders()})

    # ----- options -----------------------------------------------------

    async def chain(self, session_id: str, expiry: str | None, strikes: int = 10) -> dict:
        rt = await self.get(session_id)
        cursor = rt.clock.cursor
        day = et(cursor.ts).date()
        expiries = list_expiries(day, 30)
        chosen = next((e for e in expiries if e.isoformat() == expiry), expiries[0])
        return {
            "spot": cursor.close,
            "as_of": _epoch(cursor.end),
            "expiries": [e.isoformat() for e in expiries],
            "expiry": chosen.isoformat(),
            "atm_iv": rt.pricer.atm_iv(rt.symbol, day),
            "real_contracts": rt.real.contracts,
            "rows": rt.pricer.chain(rt.symbol, cursor.close, cursor.end, chosen, strikes),
        }

    # ----- views -------------------------------------------------------

    async def snapshot(self, session_id: str) -> dict:
        rt = await self.get(session_id)
        async with SessionLocal() as db:
            fills = (
                await db.execute(select(FillRow).where(FillRow.session_id == session_id).order_by(FillRow.ts))
            ).scalars().all()
        return {
            "session": {"id": rt.id, "symbol": rt.symbol, "starting_cash": rt.starting_cash},
            "state": rt.clock.state(),
            "bars": [b.to_dict() for b in rt.clock.visible()],
            "account": rt.engine.summary(),
            "orders": rt.orders(),
            "fills": [fill_dict(f) for f in fills],
        }

    # ----- persistence -------------------------------------------------

    async def _flush(self, rt: Runtime, durable: bool = False) -> None:
        engine = rt.engine
        new_fills = engine.fills[rt.saved_fills :]
        new_trades = engine.closed_trades[rt.saved_trades :]
        changed = [o for o in engine.orders.values() if rt.saved_orders.get(o.id) != o.status.value]
        async with SessionLocal() as db:
            for o in changed:
                await db.merge(
                    OrderRow(
                        id=o.id, session_id=rt.id, symbol=o.symbol, asset_class=o.asset_class,
                        side=o.side.value, qty=o.qty, type=o.type.value, limit_price=o.limit_price,
                        stop_price=o.stop_price, take_profit=o.take_profit, stop_loss=o.stop_loss,
                        status=o.status.value, parent_id=o.parent_id, tag=o.tag, reason=o.reason,
                        created_ts=o.created_ts, filled_ts=o.filled_ts, fill_price=o.fill_price,
                    )
                )
            db.add_all(
                FillRow(
                    session_id=rt.id, order_id=f.order_id, symbol=f.symbol, side=f.side.value, qty=f.qty,
                    price=f.price, commission=f.commission, ts=f.ts, price_source=f.price_source,
                )
                for f in new_fills
            )
            db.add_all(
                TradeRow(
                    session_id=rt.id, symbol=t.symbol, direction=t.direction, qty=t.qty,
                    entry_ts=t.entry_ts, exit_ts=t.exit_ts, entry_price=t.entry_price,
                    exit_price=t.exit_price, pnl=t.pnl, commission=t.commission,
                )
                for t in new_trades
            )
            db.add_all(
                EquityPointRow(session_id=rt.id, ts=ts, equity=eq, exposure=ex)
                for ts, eq, ex in rt.pending_equity
            )
            if new_fills:
                await db.execute(delete(PositionRow).where(PositionRow.session_id == rt.id))
                db.add_all(
                    PositionRow(
                        session_id=rt.id, symbol=p.symbol, qty=p.qty, avg_cost=p.avg_cost,
                        realized_pnl=p.realized_pnl, updated_ts=rt.clock.cursor.end,
                    )
                    for p in engine.positions.values()
                )
            row = await db.get(ReplaySession, rt.id)
            if row is not None:
                row.cursor_ts = rt.clock.cursor.ts
                row.speed = rt.clock.speed
                row.status = rt.clock.status.value
                if durable:
                    row.engine_state = engine.to_dict()
            await db.commit()
        rt.saved_fills = len(engine.fills)
        rt.saved_trades = len(engine.closed_trades)
        rt.saved_orders = {o.id: o.status.value for o in engine.orders.values()}
        rt.pending_equity.clear()
        await self._save_redis(rt)

    async def _save_redis(self, rt: Runtime) -> None:
        state = {k: str(v) for k, v in rt.clock.state().items()}
        await self.redis.hset(state_key(rt.id), mapping=state)
        await self.redis.set(engine_key(rt.id), json.dumps(rt.engine.to_dict()))

    async def _publish(self, rt: Runtime, event: dict) -> None:
        await self.redis.publish(channel(rt.id), json.dumps(event, default=str))
