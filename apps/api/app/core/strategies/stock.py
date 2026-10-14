from __future__ import annotations

from pydantic import Field

from app.core.strategy import Context, Strategy, StrategyParams


class OrbParams(StrategyParams):
    qty: int = Field(100, ge=1, title="Shares")
    range_minutes: int = Field(15, ge=1, le=120, title="Opening range (min)")
    target_multiple: float = Field(1.0, gt=0, le=10, title="Target (x range)")
    stop_at_mid: bool = Field(False, title="Stop at range midpoint", description="Otherwise the stop is the far side of the range")
    allow_short: bool = Field(True, title="Allow shorts")


class OpeningRangeBreakout(Strategy):
    name = "orb"
    label = "Opening Range Breakout"
    description = "Trades the first close outside the opening range with a bracket: target is a multiple of the range, stop is the opposite side (or midpoint)."
    Params = OrbParams
    p: OrbParams

    def on_day_start(self, ctx: Context) -> None:
        self.hi = self.lo = None
        self.traded = False

    def on_bar(self, ctx: Context) -> None:
        bar = ctx.bar
        if ctx.minutes_since_open <= self.p.range_minutes:
            self.hi = bar.high if self.hi is None else max(self.hi, bar.high)
            self.lo = bar.low if self.lo is None else min(self.lo, bar.low)
            return
        if self.traded or self.hi is None or ctx.position() != 0:
            return
        rng = self.hi - self.lo
        if rng <= 0:
            return
        mid = (self.hi + self.lo) / 2
        if bar.close > self.hi:
            stop = mid if self.p.stop_at_mid else self.lo
            ctx.buy(self.p.qty, take_profit=self.hi + rng * self.p.target_multiple, stop_loss=stop, tag="orb_long")
            self.traded = True
        elif bar.close < self.lo and self.p.allow_short:
            stop = mid if self.p.stop_at_mid else self.hi
            ctx.sell(self.p.qty, take_profit=self.lo - rng * self.p.target_multiple, stop_loss=stop, tag="orb_short")
            self.traded = True


class VwapParams(StrategyParams):
    qty: int = Field(100, ge=1, title="Shares")
    band_pct: float = Field(0.2, gt=0, le=5, title="Entry band (% from VWAP)")
    stop_pct: float = Field(0.3, gt=0, le=5, title="Stop (% from entry)")
    start_minute: int = Field(30, ge=1, le=360, title="Start after (min)")
    max_trades: int = Field(3, ge=1, le=50, title="Max trades per day")
    allow_short: bool = Field(True, title="Allow shorts")


class VwapReversion(Strategy):
    name = "vwap_reversion"
    label = "VWAP Reversion"
    description = "Fades stretches away from session VWAP, targeting a return to VWAP with a fixed percentage stop."
    Params = VwapParams
    p: VwapParams

    def on_day_start(self, ctx: Context) -> None:
        self.trades = 0

    def on_bar(self, ctx: Context) -> None:
        if ctx.minutes_since_open < self.p.start_minute or self.trades >= self.p.max_trades:
            return
        if ctx.position() != 0 or ctx.pending():
            return
        close, vwap = ctx.bar.close, ctx.vwap()
        dev = (close / vwap - 1) * 100
        stop = self.p.stop_pct / 100
        if dev <= -self.p.band_pct:
            ctx.buy(self.p.qty, take_profit=round(vwap, 2), stop_loss=round(close * (1 - stop), 2), tag="vwap_long")
            self.trades += 1
        elif dev >= self.p.band_pct and self.p.allow_short:
            ctx.sell(self.p.qty, take_profit=round(vwap, 2), stop_loss=round(close * (1 + stop), 2), tag="vwap_short")
            self.trades += 1


class MaParams(StrategyParams):
    qty: int = Field(100, ge=1, title="Shares")
    fast: int = Field(20, ge=2, le=500, title="Fast SMA (bars)")
    slow: int = Field(50, ge=3, le=2000, title="Slow SMA (bars)")
    allow_short: bool = Field(False, title="Allow shorts")
    flatten_eod: bool = Field(False, title="Flatten before close")


class MaCrossover(Strategy):
    name = "ma_crossover"
    label = "Moving Average Crossover"
    description = "Long when the fast SMA crosses above the slow SMA, exit (or reverse short) on the cross back down."
    Params = MaParams
    p: MaParams

    def on_start(self, ctx: Context) -> None:
        self.prev: int | None = None

    def on_bar(self, ctx: Context) -> None:
        fast, slow = ctx.sma(self.p.fast), ctx.sma(self.p.slow)
        if fast is None or slow is None or ctx.pending():
            return
        regime = 1 if fast > slow else -1
        if self.prev is not None and regime != self.prev:
            target = self.p.qty if regime > 0 else (-self.p.qty if self.p.allow_short else 0)
            delta = target - ctx.position()
            if delta > 0:
                ctx.buy(delta, tag="cross_up")
            elif delta < 0:
                ctx.sell(-delta, tag="cross_down")
        self.prev = regime
