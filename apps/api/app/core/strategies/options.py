from __future__ import annotations

from pydantic import Field

from app.core.strategy import Context, Strategy, StrategyParams


class StraddleParams(StrategyParams):
    qty: int = Field(1, ge=1, le=100, title="Contracts per leg")
    entry_minute: int = Field(30, ge=1, le=360, title="Enter at (min after open)")
    profit_target_pct: float = Field(50, gt=0, le=1000, title="Profit target (% of debit)")
    stop_loss_pct: float = Field(40, gt=0, le=100, title="Stop loss (% of debit)")
    flatten_minutes: int = Field(15, ge=1, le=120, title="Flatten minutes before close")


class ZeroDteStraddle(Strategy):
    name = "zero_dte_straddle"
    label = "0DTE Long Straddle"
    description = "Buys the at-the-money call and put expiring today at a fixed time, exiting on a profit target, a stop, or before the close."
    uses_options = True
    Params = StraddleParams
    p: StraddleParams

    def on_day_start(self, ctx: Context) -> None:
        self.legs: list[str] = []
        self.debit: float | None = None
        self.done = False

    def on_bar(self, ctx: Context) -> None:
        if self.done:
            return
        if not self.legs:
            if ctx.minutes_since_open >= self.p.entry_minute:
                self.legs = [ctx.option("C", dte=0), ctx.option("P", dte=0)]
                for leg in self.legs:
                    ctx.buy(self.p.qty, symbol=leg, tag="straddle")
            return
        if any(ctx.position(leg) == 0 for leg in self.legs):
            return
        if self.debit is None:
            self.debit = sum(ctx.avg_cost(leg) for leg in self.legs)
        value = sum(ctx.option_quote(leg).price for leg in self.legs)
        if value >= self.debit * (1 + self.p.profit_target_pct / 100) or value <= self.debit * (
            1 - self.p.stop_loss_pct / 100
        ):
            ctx.close_all()
            self.done = True


class CondorParams(StrategyParams):
    qty: int = Field(1, ge=1, le=100, title="Condors")
    entry_minute: int = Field(30, ge=1, le=360, title="Enter at (min after open)")
    short_offset: float = Field(5, gt=0, le=50, title="Short strikes ($ from spot)")
    wing_width: float = Field(5, gt=0, le=50, title="Wing width ($)")
    take_profit_pct: float = Field(50, gt=0, le=100, title="Take profit (% of credit)")
    stop_loss_multiple: float = Field(2.0, gt=0, le=10, title="Stop loss (x credit)")
    flatten_minutes: int = Field(15, ge=1, le=120, title="Flatten minutes before close")
    flatten_eod: bool = Field(True, title="Flatten before close", description="Turn off to hold to expiry and cash-settle at intrinsic value")


class ZeroDteIronCondor(Strategy):
    name = "zero_dte_iron_condor"
    label = "0DTE Short Iron Condor"
    description = "Sells an out-of-the-money call spread and put spread expiring today, managing on a percentage-of-credit target and a credit-multiple stop."
    uses_options = True
    Params = CondorParams
    p: CondorParams

    def on_day_start(self, ctx: Context) -> None:
        self.shorts: list[str] = []
        self.longs: list[str] = []
        self.credit: float | None = None
        self.done = False

    def on_bar(self, ctx: Context) -> None:
        if self.done:
            return
        p = self.p
        if not self.shorts:
            if ctx.minutes_since_open >= p.entry_minute:
                off, w = p.short_offset, p.wing_width
                self.longs = [ctx.option("C", 0, off + w), ctx.option("P", 0, -off - w)]
                self.shorts = [ctx.option("C", 0, off), ctx.option("P", 0, -off)]
                for leg in self.longs:
                    ctx.buy(p.qty, symbol=leg, tag="condor_wing")
                for leg in self.shorts:
                    ctx.sell(p.qty, symbol=leg, tag="condor_short")
            return
        legs = self.shorts + self.longs
        if any(ctx.position(leg) == 0 for leg in legs):
            return
        if self.credit is None:
            self.credit = sum(ctx.avg_cost(s) for s in self.shorts) - sum(ctx.avg_cost(lg) for lg in self.longs)
            if self.credit <= 0:
                ctx.close_all()
                self.done = True
                return
        cost_to_close = sum(ctx.option_quote(s).price for s in self.shorts) - sum(
            ctx.option_quote(lg).price for lg in self.longs
        )
        if cost_to_close <= self.credit * (1 - p.take_profit_pct / 100) or cost_to_close >= self.credit * (
            1 + p.stop_loss_multiple
        ):
            ctx.close_all()
            self.done = True
