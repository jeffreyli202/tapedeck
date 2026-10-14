"""Order matching and portfolio accounting shared by paper trading and backtests.

Orders only ever fill against bars that *start after* the order was placed, so
whatever the trader (or strategy) saw when deciding can never be the bar it
trades on.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import StrEnum

from app.core.occ import is_option, multiplier, parse_occ, underlying_of
from app.core.types import Bar

SHORT_STOCK_MARGIN = 0.5
SHORT_OPTION_MARGIN = 0.2


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderStatus(StrEnum):
    OPEN = "open"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"


@dataclass
class Order:
    symbol: str
    side: Side
    qty: int
    type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    stop_price: float | None = None
    take_profit: float | None = None
    stop_loss: float | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: OrderStatus = OrderStatus.OPEN
    created_ts: datetime | None = None
    filled_ts: datetime | None = None
    fill_price: float | None = None
    parent_id: str | None = None
    oco_group: str | None = None
    reason: str | None = None
    tag: str | None = None

    @property
    def asset_class(self) -> str:
        return "option" if is_option(self.symbol) else "stock"

    @property
    def signed_qty(self) -> int:
        return self.qty if self.side == Side.BUY else -self.qty

    @property
    def is_bracket(self) -> bool:
        return self.take_profit is not None or self.stop_loss is not None


@dataclass
class Fill:
    order_id: str
    symbol: str
    side: Side
    qty: int
    price: float
    commission: float
    ts: datetime
    price_source: str = "real"


@dataclass
class Position:
    symbol: str
    qty: int = 0
    avg_cost: float = 0.0
    realized_pnl: float = 0.0
    opened_ts: datetime | None = None
    entry_commission: float = 0.0


@dataclass
class ClosedTrade:
    symbol: str
    direction: str  # "long" or "short"
    qty: int
    entry_ts: datetime
    exit_ts: datetime
    entry_price: float
    exit_price: float
    pnl: float  # net of commissions
    commission: float


@dataclass
class FillConfig:
    stock_slippage_bps: float = 1.0
    option_slippage_pct: float = 0.01
    option_min_slippage: float = 0.01
    stock_commission_per_share: float = 0.0
    option_commission_per_contract: float = 0.65
    limit_requires_trade_through: bool = True


class OrderRejected(Exception):
    pass


class FillEngine:
    def __init__(self, cash: float, config: FillConfig | None = None):
        self.cash = cash
        self.config = config or FillConfig()
        self.orders: dict[str, Order] = {}
        self.positions: dict[str, Position] = {}
        self.fills: list[Fill] = []
        self.closed_trades: list[ClosedTrade] = []
        self.last_prices: dict[str, float] = {}

    # ----- order entry -------------------------------------------------

    def submit(self, order: Order, now: datetime) -> Order:
        order.created_ts = now
        try:
            self._validate(order)
        except OrderRejected as exc:
            order.status = OrderStatus.REJECTED
            order.reason = str(exc)
            self.orders[order.id] = order
            return order
        self.orders[order.id] = order
        return order

    def cancel(self, order_id: str, reason: str = "canceled by user") -> Order | None:
        order = self.orders.get(order_id)
        if order and order.status == OrderStatus.OPEN:
            order.status = OrderStatus.CANCELED
            order.reason = reason
        return order

    def cancel_all(self, symbol: str | None = None, reason: str = "canceled") -> None:
        for o in self.open_orders(symbol):
            self.cancel(o.id, reason)

    def open_orders(self, symbol: str | None = None) -> list[Order]:
        return [
            o
            for o in self.orders.values()
            if o.status == OrderStatus.OPEN and (symbol is None or o.symbol == symbol)
        ]

    def _validate(self, order: Order) -> None:
        if order.qty <= 0:
            raise OrderRejected("quantity must be positive")
        if order.type == OrderType.LIMIT and not order.limit_price:
            raise OrderRejected("limit order needs a limit price")
        if order.type == OrderType.STOP and not order.stop_price:
            raise OrderRejected("stop order needs a stop price")
        if order.parent_id:
            return

        ref = order.limit_price or order.stop_price or self.last_prices.get(order.symbol)
        if ref is None:
            raise OrderRejected(f"no price available for {order.symbol}")

        pos_qty = self.position_qty(order.symbol)
        new_qty = pos_qty + order.signed_qty
        opening = abs(new_qty) > abs(pos_qty) or (pos_qty != 0 and new_qty * pos_qty < 0)
        if not opening:
            return
        opened_qty = abs(new_qty) - (abs(pos_qty) if new_qty * pos_qty > 0 else 0)
        mult = multiplier(order.symbol)
        if new_qty > 0:
            required = ref * opened_qty * mult + self._commission(order.symbol, opened_qty)
        elif is_option(order.symbol):
            spot = self.last_prices.get(underlying_of(order.symbol), ref)
            required = SHORT_OPTION_MARGIN * spot * opened_qty * mult
        else:
            required = SHORT_STOCK_MARGIN * ref * opened_qty
        if required > self.buying_power() + 1e-9:
            raise OrderRejected(
                f"insufficient buying power: need {required:,.2f}, have {self.buying_power():,.2f}"
            )

    # ----- matching ----------------------------------------------------

    def on_bar(self, symbol: str, bar: Bar, price_source: str = "real") -> list[Fill]:
        """Match open orders for `symbol` against `bar`, then mark to its close."""
        fills: list[Fill] = []
        candidates = [
            o
            for o in self.open_orders(symbol)
            if o.created_ts is not None and o.created_ts < bar.ts
        ]
        # When both legs of an OCO bracket trigger in the same bar we cannot know
        # which traded first, so assume the stop (the worse outcome) did.
        candidates.sort(key=lambda o: (o.oco_group is None, o.type != OrderType.STOP))
        for order in candidates:
            if order.status != OrderStatus.OPEN:
                continue
            price = self._match_price(order, bar)
            if price is None:
                continue
            fills.append(self._execute(order, price, bar.ts, price_source))
            if order.oco_group:
                for sibling in self.open_orders(symbol):
                    if sibling.oco_group == order.oco_group:
                        self.cancel(sibling.id, "OCO sibling filled")
            if order.is_bracket:
                self._spawn_bracket_legs(order, bar.ts)
        self.last_prices[symbol] = bar.close
        return fills

    def _match_price(self, order: Order, bar: Bar) -> float | None:
        buy = order.side == Side.BUY
        if order.type == OrderType.MARKET:
            return self._slip(order.symbol, bar.open, buy)
        if order.type == OrderType.LIMIT:
            lim = order.limit_price
            if buy:
                if bar.open <= lim:
                    return bar.open
                hit = bar.low < lim if self.config.limit_requires_trade_through else bar.low <= lim
            else:
                if bar.open >= lim:
                    return bar.open
                hit = bar.high > lim if self.config.limit_requires_trade_through else bar.high >= lim
            return lim if hit else None
        stop = order.stop_price
        if buy:
            if bar.open >= stop:
                return self._slip(order.symbol, bar.open, True)
            return self._slip(order.symbol, stop, True) if bar.high >= stop else None
        if bar.open <= stop:
            return self._slip(order.symbol, bar.open, False)
        return self._slip(order.symbol, stop, False) if bar.low <= stop else None

    def _slip(self, symbol: str, price: float, buy: bool) -> float:
        if is_option(symbol):
            slip = max(self.config.option_min_slippage, price * self.config.option_slippage_pct)
            return round(price + slip, 2) if buy else max(0.01, round(price - slip, 2))
        slip = price * self.config.stock_slippage_bps / 10_000
        return price + slip if buy else price - slip

    def _commission(self, symbol: str, qty: int) -> float:
        if is_option(symbol):
            return self.config.option_commission_per_contract * qty
        return self.config.stock_commission_per_share * qty

    def _spawn_bracket_legs(self, parent: Order, ts: datetime) -> None:
        exit_side = Side.SELL if parent.side == Side.BUY else Side.BUY
        group = parent.id
        if parent.take_profit is not None:
            self.orders_add(
                Order(
                    symbol=parent.symbol,
                    side=exit_side,
                    qty=parent.qty,
                    type=OrderType.LIMIT,
                    limit_price=parent.take_profit,
                    parent_id=parent.id,
                    oco_group=group,
                    tag="take_profit",
                ),
                ts,
            )
        if parent.stop_loss is not None:
            self.orders_add(
                Order(
                    symbol=parent.symbol,
                    side=exit_side,
                    qty=parent.qty,
                    type=OrderType.STOP,
                    stop_price=parent.stop_loss,
                    parent_id=parent.id,
                    oco_group=group,
                    tag="stop_loss",
                ),
                ts,
            )

    def orders_add(self, order: Order, ts: datetime) -> None:
        order.created_ts = ts
        self.orders[order.id] = order

    # ----- accounting --------------------------------------------------

    def _execute(self, order: Order, price: float, ts: datetime, source: str) -> Fill:
        commission = self._commission(order.symbol, order.qty)
        mult = multiplier(order.symbol)
        notional = price * order.qty * mult
        self.cash += -notional if order.side == Side.BUY else notional
        self.cash -= commission
        self._apply_to_position(order.symbol, order.signed_qty, price, ts, commission)
        order.status = OrderStatus.FILLED
        order.filled_ts = ts
        order.fill_price = price
        fill = Fill(order.id, order.symbol, order.side, order.qty, price, commission, ts, source)
        self.fills.append(fill)
        return fill

    def _apply_to_position(
        self, symbol: str, dq: int, price: float, ts: datetime, commission: float
    ) -> None:
        pos = self.positions.setdefault(symbol, Position(symbol))
        mult = multiplier(symbol)
        if pos.qty == 0 or (pos.qty > 0) == (dq > 0):
            total = abs(pos.qty) + abs(dq)
            pos.avg_cost = (pos.avg_cost * abs(pos.qty) + price * abs(dq)) / total
            if pos.qty == 0:
                pos.opened_ts = ts
            pos.qty += dq
            pos.entry_commission += commission
            return

        closing = min(abs(dq), abs(pos.qty))
        direction = 1 if pos.qty > 0 else -1
        gross = (price - pos.avg_cost) * closing * direction * mult
        entry_comm = pos.entry_commission * closing / abs(pos.qty)
        exit_comm = commission * closing / abs(dq)
        pos.entry_commission -= entry_comm
        pos.realized_pnl += gross
        self.closed_trades.append(
            ClosedTrade(
                symbol=symbol,
                direction="long" if direction > 0 else "short",
                qty=closing,
                entry_ts=pos.opened_ts or ts,
                exit_ts=ts,
                entry_price=pos.avg_cost,
                exit_price=price,
                pnl=gross - entry_comm - exit_comm,
                commission=entry_comm + exit_comm,
            )
        )
        pos.qty += direction * -closing
        remainder = abs(dq) - closing
        if pos.qty == 0:
            pos.avg_cost = 0.0
            pos.entry_commission = 0.0
            pos.opened_ts = None
        if remainder:
            pos.qty = remainder * (1 if dq > 0 else -1)
            pos.avg_cost = price
            pos.opened_ts = ts
            pos.entry_commission = commission - exit_comm

    def settle_expiries(self, day: date, ts: datetime) -> list[Fill]:
        """Cash-settle option positions expiring on `day` at intrinsic value."""
        fills: list[Fill] = []
        for symbol, pos in list(self.positions.items()):
            spec = parse_occ(symbol)
            if not spec or spec.expiry > day:
                continue
            self.cancel_all(symbol, "contract expired")
            if pos.qty == 0:
                continue
            spot = self.last_prices.get(spec.underlying)
            if spot is None:
                continue
            intrinsic = max(0.0, spot - spec.strike if spec.right == "C" else spec.strike - spot)
            side = Side.SELL if pos.qty > 0 else Side.BUY
            order = Order(symbol=symbol, side=side, qty=abs(pos.qty), tag="expiry")
            order.created_ts = ts
            self.orders[order.id] = order
            fill = self._execute(order, round(intrinsic, 4), ts, "settlement")
            # settlement carries no commission
            self.cash += fill.commission
            fill.commission = 0.0
            fills.append(fill)
            self.last_prices[symbol] = intrinsic
        return fills

    # ----- views -------------------------------------------------------

    def position_qty(self, symbol: str) -> int:
        pos = self.positions.get(symbol)
        return pos.qty if pos else 0

    def open_positions(self) -> list[Position]:
        return [p for p in self.positions.values() if p.qty != 0]

    def market_value(self, symbol: str) -> float:
        pos = self.positions.get(symbol)
        if not pos or pos.qty == 0:
            return 0.0
        price = self.last_prices.get(symbol, pos.avg_cost)
        return pos.qty * price * multiplier(symbol)

    def unrealized_pnl(self, symbol: str) -> float:
        pos = self.positions.get(symbol)
        if not pos or pos.qty == 0:
            return 0.0
        return self.market_value(symbol) - pos.qty * pos.avg_cost * multiplier(symbol)

    def equity(self) -> float:
        return self.cash + sum(self.market_value(p.symbol) for p in self.open_positions())

    def gross_exposure(self) -> float:
        return sum(abs(self.market_value(p.symbol)) for p in self.open_positions())

    def reserved_margin(self) -> float:
        reserved = 0.0
        for p in self.open_positions():
            if p.qty >= 0:
                continue
            mv = abs(self.market_value(p.symbol))
            if is_option(p.symbol):
                spot = self.last_prices.get(underlying_of(p.symbol), 0.0)
                reserved += mv + SHORT_OPTION_MARGIN * spot * abs(p.qty) * multiplier(p.symbol)
            else:
                reserved += mv * (1 + SHORT_STOCK_MARGIN)
        return reserved

    def buying_power(self) -> float:
        return max(0.0, self.cash - self.reserved_margin())

    def realized_pnl(self) -> float:
        return sum(p.realized_pnl for p in self.positions.values())

    def summary(self) -> dict:
        return {
            "cash": self.cash,
            "equity": self.equity(),
            "buying_power": self.buying_power(),
            "realized_pnl": self.realized_pnl(),
            "unrealized_pnl": sum(self.unrealized_pnl(p.symbol) for p in self.open_positions()),
            "positions": [
                {
                    "symbol": p.symbol,
                    "asset_class": "option" if is_option(p.symbol) else "stock",
                    "qty": p.qty,
                    "avg_cost": p.avg_cost,
                    "last": self.last_prices.get(p.symbol),
                    "market_value": self.market_value(p.symbol),
                    "unrealized_pnl": self.unrealized_pnl(p.symbol),
                    "realized_pnl": p.realized_pnl,
                }
                for p in self.open_positions()
            ],
        }

    # ----- persistence -------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "cash": self.cash,
            "config": asdict(self.config),
            "orders": [_dump(asdict(o)) for o in self.orders.values()],
            "positions": [_dump(asdict(p)) for p in self.positions.values()],
            "closed_trades": [_dump(asdict(t)) for t in self.closed_trades],
            "last_prices": self.last_prices,
        }

    @classmethod
    def from_dict(cls, data: dict) -> FillEngine:
        engine = cls(data["cash"], FillConfig(**data["config"]))
        for o in data["orders"]:
            o = _load(o, ("created_ts", "filled_ts"))
            o["side"] = Side(o["side"])
            o["type"] = OrderType(o["type"])
            o["status"] = OrderStatus(o["status"])
            order = Order(**o)
            engine.orders[order.id] = order
        for p in data["positions"]:
            pos = Position(**_load(p, ("opened_ts",)))
            engine.positions[pos.symbol] = pos
        engine.closed_trades = [
            ClosedTrade(**_load(t, ("entry_ts", "exit_ts"))) for t in data["closed_trades"]
        ]
        engine.last_prices = dict(data["last_prices"])
        return engine


def _dump(d: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in d.items()}


def _load(d: dict, ts_keys: tuple[str, ...]) -> dict:
    d = dict(d)
    for k in ts_keys:
        if d.get(k):
            d[k] = datetime.fromisoformat(d[k])
    return d
