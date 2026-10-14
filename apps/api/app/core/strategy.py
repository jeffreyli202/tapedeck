"""Strategy API and the backtest loop that drives it through the FillEngine."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import ClassVar

from pydantic import BaseModel, Field

from app.core.fill_engine import FillEngine, Order, OrderType, Side
from app.core.metrics import EquityPoint, TradeRecord, compute_metrics
from app.core.occ import is_option, parse_occ
from app.core.pricer import OptionPricer, OptionQuote, list_expiries
from app.core.types import Bar, et, minutes_since_open, minutes_to_close


class StrategyParams(BaseModel):
    flatten_eod: bool = Field(True, title="Flatten before close", description="Exit all positions near the close each day")
    flatten_minutes: int = Field(5, ge=1, le=120, title="Flatten minutes before close")


class Strategy:
    name: ClassVar[str]
    label: ClassVar[str]
    description: ClassVar[str]
    uses_options: ClassVar[bool] = False
    Params: ClassVar[type[StrategyParams]] = StrategyParams

    def __init__(self, params: StrategyParams):
        self.p = params

    def on_start(self, ctx: Context) -> None: ...
    def on_day_start(self, ctx: Context) -> None: ...
    def on_bar(self, ctx: Context) -> None: ...
    def on_day_end(self, ctx: Context) -> None: ...

    @classmethod
    def schema(cls) -> dict:
        return {
            "name": cls.name,
            "label": cls.label,
            "description": cls.description,
            "uses_options": cls.uses_options,
            "params": cls.Params.model_json_schema(),
        }


class Context:
    """What a strategy sees on each bar. History stops at the current bar."""

    def __init__(self, symbol: str, bars: list[Bar], engine: FillEngine, pricer: OptionPricer):
        self.symbol = symbol
        self._bars = bars
        self.engine = engine
        self.pricer = pricer
        self.i = -1
        self.day_start = 0
        self._cum_pv = 0.0
        self._cum_v = 0.0
        self._ema: dict[int, float] = {}

    # --- clock -------------------------------------------------------------

    @property
    def bar(self) -> Bar:
        return self._bars[self.i]

    @property
    def now(self) -> datetime:
        return self.bar.end

    @property
    def minutes_since_open(self) -> float:
        return minutes_since_open(self.now)

    @property
    def minutes_to_close(self) -> float:
        return minutes_to_close(self.now)

    def history(self, n: int) -> list[Bar]:
        return self._bars[max(0, self.i - n + 1) : self.i + 1]

    def day_bars(self) -> list[Bar]:
        return self._bars[self.day_start : self.i + 1]

    def _advance(self, i: int, new_day: bool) -> None:
        self.i = i
        if new_day:
            self.day_start = i
            self._cum_pv = self._cum_v = 0.0
        b = self.bar
        typical = b.vwap if b.vwap else (b.high + b.low + b.close) / 3
        vol = b.volume or 1.0
        self._cum_pv += typical * vol
        self._cum_v += vol
        for n, prev in list(self._ema.items()):
            k = 2 / (n + 1)
            self._ema[n] = b.close * k + prev * (1 - k)

    # --- indicators --------------------------------------------------------

    def sma(self, n: int) -> float | None:
        if self.i + 1 < n:
            return None
        return sum(b.close for b in self.history(n)) / n

    def ema(self, n: int) -> float:
        if n not in self._ema:
            seed = self.history(n)
            self._ema[n] = sum(b.close for b in seed) / len(seed)
        return self._ema[n]

    def vwap(self) -> float:
        return self._cum_pv / self._cum_v if self._cum_v else self.bar.close

    # --- account -----------------------------------------------------------

    def position(self, symbol: str | None = None) -> int:
        return self.engine.position_qty(symbol or self.symbol)

    def avg_cost(self, symbol: str) -> float:
        pos = self.engine.positions.get(symbol)
        return pos.avg_cost if pos else 0.0

    @property
    def equity(self) -> float:
        return self.engine.equity()

    @property
    def cash(self) -> float:
        return self.engine.cash

    def pending(self, symbol: str | None = None) -> list[Order]:
        return [o for o in self.engine.open_orders(symbol) if o.parent_id is None]

    # --- orders ------------------------------------------------------------

    def order(
        self,
        side: Side,
        qty: int,
        symbol: str | None = None,
        type: OrderType = OrderType.MARKET,
        limit: float | None = None,
        stop: float | None = None,
        take_profit: float | None = None,
        stop_loss: float | None = None,
        tag: str | None = None,
    ) -> Order:
        symbol = symbol or self.symbol
        if is_option(symbol) and symbol not in self.engine.last_prices:
            self.engine.last_prices[symbol] = self.option_quote(symbol).price
        o = Order(
            symbol=symbol, side=side, qty=qty, type=type, limit_price=limit, stop_price=stop,
            take_profit=take_profit, stop_loss=stop_loss, tag=tag,
        )
        return self.engine.submit(o, self.bar.ts)

    def buy(self, qty: int, symbol: str | None = None, **kw) -> Order:
        return self.order(Side.BUY, qty, symbol, **kw)

    def sell(self, qty: int, symbol: str | None = None, **kw) -> Order:
        return self.order(Side.SELL, qty, symbol, **kw)

    def close(self, symbol: str | None = None) -> Order | None:
        symbol = symbol or self.symbol
        self.engine.cancel_all(symbol, "position closed")
        qty = self.position(symbol)
        if qty == 0:
            return None
        return self.order(Side.SELL if qty > 0 else Side.BUY, abs(qty), symbol, tag="close")

    def close_all(self) -> None:
        self.engine.cancel_all(reason="flatten")
        for p in self.engine.open_positions():
            self.close(p.symbol)

    # --- options -----------------------------------------------------------

    def option(self, right: str, dte: int = 0, offset: float = 0.0) -> str:
        """Pick a contract `offset` dollars from spot, expiring `dte` days out
        (rounded to the next listed expiry)."""
        today = et(self.now).date()
        expiry = list_expiries(today, max(dte, 0) + 7)
        target = next(d for d in expiry if (d - today).days >= dte)
        return self.pricer.pick(self.symbol, self.bar.close, right, target, offset)

    def option_quote(self, symbol: str) -> OptionQuote:
        spec = parse_occ(symbol)
        return self.pricer.quote(spec, self.bar.close, self.now)


@dataclass
class BacktestResult:
    equity: list[EquityPoint]
    trades: list
    fills: list
    metrics: dict
    orders: list = field(default_factory=list)


ProgressFn = Callable[[float], None]


class Backtester:
    def __init__(
        self,
        strategy: Strategy,
        symbol: str,
        bars: list[Bar],
        engine: FillEngine,
        pricer: OptionPricer,
        progress: ProgressFn | None = None,
        on_new_day: Callable[[date], None] | None = None,
    ):
        self.strategy = strategy
        self.symbol = symbol
        self.bars = bars
        self.engine = engine
        self.pricer = pricer
        self.progress = progress
        self.on_new_day = on_new_day
        self.starting_cash = engine.cash

    def run(self) -> BacktestResult:
        ctx = Context(self.symbol, self.bars, self.engine, self.pricer)
        points: list[EquityPoint] = []
        n = len(self.bars)
        self.strategy.on_start(ctx)
        step = max(1, n // 100)
        for i, bar in enumerate(self.bars):
            day = et(bar.ts).date()
            new_day = i == 0 or et(self.bars[i - 1].ts).date() != day
            if new_day and self.on_new_day:
                self.on_new_day(day)
            self._match(bar)
            ctx._advance(i, new_day)
            if new_day:
                self.strategy.on_day_start(ctx)

            p = self.strategy.p
            if p.flatten_eod and ctx.minutes_to_close <= p.flatten_minutes:
                if self.engine.open_positions() or ctx.pending():
                    ctx.close_all()
            else:
                self.strategy.on_bar(ctx)

            day_end = i == n - 1 or et(self.bars[i + 1].ts).date() != day
            if day_end:
                self.strategy.on_day_end(ctx)
                for o in self.engine.open_orders():
                    if o.parent_id is None:
                        self.engine.cancel(o.id, "day order expired")
                self.engine.settle_expiries(day, bar.end)

            points.append(
                EquityPoint(bar.end, self.engine.equity(), self.engine.gross_exposure())
            )
            if self.progress and (i % step == 0 or i == n - 1):
                self.progress((i + 1) / n)

        trades = [
            TradeRecord(t.pnl, t.entry_ts, t.exit_ts, t.direction) for t in self.engine.closed_trades
        ]
        return BacktestResult(
            equity=points,
            trades=self.engine.closed_trades,
            fills=self.engine.fills,
            metrics=compute_metrics(points, trades, self.starting_cash),
            orders=list(self.engine.orders.values()),
        )

    def _match(self, bar: Bar) -> None:
        self.engine.on_bar(self.symbol, bar)
        option_symbols = {o.symbol for o in self.engine.open_orders() if is_option(o.symbol)}
        option_symbols |= {p.symbol for p in self.engine.open_positions() if is_option(p.symbol)}
        for sym in option_symbols:
            spec = parse_occ(sym)
            if spec is None or spec.expiry < et(bar.ts).date():
                continue
            obar, source = self.pricer.option_bar(sym, bar)
            self.engine.on_bar(sym, obar, source)
