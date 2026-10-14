from app.core.strategies.options import ZeroDteIronCondor, ZeroDteStraddle
from app.core.strategies.stock import MaCrossover, OpeningRangeBreakout, VwapReversion
from app.core.strategy import Strategy

STRATEGIES: dict[str, type[Strategy]] = {
    s.name: s
    for s in (OpeningRangeBreakout, VwapReversion, MaCrossover, ZeroDteStraddle, ZeroDteIronCondor)
}


def build_strategy(name: str, params: dict) -> Strategy:
    cls = STRATEGIES.get(name)
    if cls is None:
        raise KeyError(f"unknown strategy: {name}")
    return cls(cls.Params(**params))
