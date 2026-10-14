"""Hybrid option pricing: real Alpaca option bars when we have them, otherwise
Black-Scholes with implied volatility proxied from VIX (SPY) or VXN (QQQ)."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta

from scipy.optimize import brentq
from scipy.stats import norm

from app.core.occ import OptionSpec, occ_symbol, parse_occ
from app.core.types import BAR_SECONDS, ET, MARKET_CLOSE, Bar

MINUTES_PER_YEAR = 365 * 24 * 60
MIN_T = 1 / MINUTES_PER_YEAR
VOL_INDEX = {"SPY": "VIX", "QQQ": "VXN"}
DEFAULT_IV = 0.18
# VIX is a 30-day variance-swap level and sits above at-the-money IV.
VIX_TO_ATM = 0.9

IvLookup = Callable[[str, date], float | None]
# Latest real option bar starting at or before the given time, or None if the
# contract has not traded recently.
RealLookup = Callable[[str, datetime], Bar | None]


@dataclass
class OptionQuote:
    symbol: str
    underlying: str
    expiry: date
    right: str
    strike: float
    price: float
    iv: float
    delta: float
    gamma: float
    theta: float
    vega: float
    source: str  # "real" or "model"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["expiry"] = self.expiry.isoformat()
        return d


def year_fraction(now: datetime, expiry: date) -> float:
    expires_at = datetime.combine(expiry, MARKET_CLOSE, tzinfo=ET)
    return max(MIN_T, (expires_at - now).total_seconds() / 60 / MINUTES_PER_YEAR)


def _d1_d2(S: float, K: float, T: float, r: float, sigma: float) -> tuple[float, float]:
    vt = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / vt
    return d1, d1 - vt


def bs_price(S: float, K: float, T: float, r: float, sigma: float, right: str) -> float:
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    disc = math.exp(-r * T)
    if right == "C":
        return S * norm.cdf(d1) - K * disc * norm.cdf(d2)
    return K * disc * norm.cdf(-d2) - S * norm.cdf(-d1)


def bs_greeks(S: float, K: float, T: float, r: float, sigma: float, right: str) -> dict:
    """Delta, gamma, theta per calendar day, vega per 1 vol point."""
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    pdf = norm.pdf(d1)
    disc = math.exp(-r * T)
    gamma = pdf / (S * sigma * math.sqrt(T))
    vega = S * pdf * math.sqrt(T) / 100
    decay = -S * pdf * sigma / (2 * math.sqrt(T))
    if right == "C":
        delta = norm.cdf(d1)
        theta = decay - r * K * disc * norm.cdf(d2)
    else:
        delta = norm.cdf(d1) - 1
        theta = decay + r * K * disc * norm.cdf(-d2)
    return {"delta": delta, "gamma": gamma, "theta": theta / 365, "vega": vega}


def implied_vol(price: float, S: float, K: float, T: float, r: float, right: str) -> float | None:
    intrinsic = max(0.0, S - K * math.exp(-r * T)) if right == "C" else max(0.0, K * math.exp(-r * T) - S)
    if price <= intrinsic + 1e-6:
        return None
    try:
        return brentq(lambda s: bs_price(S, K, T, r, s, right) - price, 1e-4, 5.0, xtol=1e-6)
    except ValueError:
        return None


def skewed_iv(atm_iv: float, S: float, K: float, T: float) -> float:
    """Downside skew: lower strikes get higher vol. Moneyness is normalized to a
    one-month horizon so short-dated smiles are steeper per dollar of strike."""
    horizon = math.sqrt(max(T, 1 / 365) / (30 / 365))
    x = math.log(K / S) / horizon
    iv = atm_iv * (1 - 1.5 * x + 2.0 * x * x)
    return min(max(iv, 0.5 * atm_iv), 3 * atm_iv)


def list_expiries(day: date, max_dte: int = 30) -> list[date]:
    """Daily expiries for the next week, then Fridays out to `max_dte`."""
    out = []
    for i in range(max_dte + 1):
        d = day + timedelta(days=i)
        if d.weekday() >= 5:
            continue
        if i <= 7 or d.weekday() == 4:
            out.append(d)
    return out


def strike_grid(spot: float, n_each_side: int = 10, step: float = 1.0) -> list[float]:
    atm = round(spot / step) * step
    return [atm + step * i for i in range(-n_each_side, n_each_side + 1)]


class OptionPricer:
    def __init__(
        self,
        risk_free_rate: float = 0.04,
        iv_lookup: IvLookup | None = None,
        real_lookup: RealLookup | None = None,
    ):
        self.r = risk_free_rate
        self.iv_lookup = iv_lookup or (lambda _u, _d: None)
        self.real_lookup = real_lookup

    def atm_iv(self, underlying: str, day: date) -> float:
        level = self.iv_lookup(VOL_INDEX.get(underlying, "VIX"), day)
        return level / 100 * VIX_TO_ATM if level else DEFAULT_IV

    def model_iv(self, spec: OptionSpec, spot: float, now: datetime) -> float:
        T = year_fraction(now, spec.expiry)
        return skewed_iv(self.atm_iv(spec.underlying, now.astimezone(ET).date()), spot, spec.strike, T)

    def model_price(self, spec: OptionSpec, spot: float, now: datetime) -> float:
        T = year_fraction(now, spec.expiry)
        sigma = self.model_iv(spec, spot, now)
        return max(0.01, bs_price(spot, spec.strike, T, self.r, sigma, spec.right))

    def quote(self, spec: OptionSpec, spot: float, now: datetime) -> OptionQuote:
        T = year_fraction(now, spec.expiry)
        last_complete = now - timedelta(seconds=BAR_SECONDS)
        real = self.real_lookup(spec.symbol, last_complete) if self.real_lookup else None
        if real is not None:
            price = real.close
            sigma = implied_vol(price, spot, spec.strike, T, self.r, spec.right)
            sigma = sigma or self.model_iv(spec, spot, now)
            source = "real"
        else:
            sigma = self.model_iv(spec, spot, now)
            price = max(0.01, bs_price(spot, spec.strike, T, self.r, sigma, spec.right))
            source = "model"
        g = bs_greeks(spot, spec.strike, T, self.r, sigma, spec.right)
        return OptionQuote(
            spec.symbol, spec.underlying, spec.expiry, spec.right, spec.strike,
            round(price, 2), sigma, g["delta"], g["gamma"], g["theta"], g["vega"], source,
        )

    def option_bar(self, symbol: str, underlying_bar: Bar) -> tuple[Bar, str]:
        """The option's bar for the same minute as `underlying_bar`: the real bar if
        it traded that minute, a flat bar at the last real trade if it traded
        recently, otherwise OHLC priced off the underlying's OHLC."""
        spec = parse_occ(symbol)
        if spec is None:
            raise ValueError(f"not an option symbol: {symbol}")
        if self.real_lookup:
            real = self.real_lookup(symbol, underlying_bar.ts)
            if real is not None:
                if real.ts == underlying_bar.ts:
                    return real, "real"
                c = real.close
                return Bar(underlying_bar.ts, c, c, c, c), "stale"
        now = underlying_bar.end
        p = {k: self.model_price(spec, getattr(underlying_bar, k), now) for k in ("open", "high", "low", "close")}
        hi, lo = (p["high"], p["low"]) if spec.right == "C" else (p["low"], p["high"])
        bar = Bar(
            underlying_bar.ts,
            round(p["open"], 2),
            round(max(hi, p["open"], p["close"]), 2),
            round(min(lo, p["open"], p["close"]), 2),
            round(p["close"], 2),
        )
        return bar, "model"

    def chain(
        self,
        underlying: str,
        spot: float,
        now: datetime,
        expiry: date,
        n_each_side: int = 10,
        step: float = 1.0,
    ) -> list[dict]:
        rows = []
        for k in strike_grid(spot, n_each_side, step):
            call = self.quote(OptionSpec(underlying, expiry, "C", k), spot, now)
            put = self.quote(OptionSpec(underlying, expiry, "P", k), spot, now)
            rows.append({"strike": k, "call": call.to_dict(), "put": put.to_dict()})
        return rows

    @staticmethod
    def pick(underlying: str, spot: float, right: str, expiry: date, offset: float = 0.0) -> str:
        """Contract `offset` dollars from at-the-money (positive = higher strike)."""
        return occ_symbol(underlying, expiry, right, round(spot + offset))
