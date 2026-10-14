import math
from datetime import date, datetime, timedelta

import pytest

from app.core.occ import OptionSpec, occ_symbol, parse_occ
from app.core.pricer import (
    OptionPricer,
    bs_greeks,
    bs_price,
    implied_vol,
    list_expiries,
    skewed_iv,
    year_fraction,
)
from app.core.types import ET, Bar


def test_occ_round_trip():
    sym = occ_symbol("SPY", date(2024, 3, 15), "P", 512.5)
    assert sym == "SPY240315P00512500"
    spec = parse_occ(sym)
    assert spec == OptionSpec("SPY", date(2024, 3, 15), "P", 512.5)
    assert parse_occ("SPY") is None


def test_put_call_parity():
    S, K, T, r, s = 500, 505, 30 / 365, 0.04, 0.2
    c, p = bs_price(S, K, T, r, s, "C"), bs_price(S, K, T, r, s, "P")
    assert c - p == pytest.approx(S - K * math.exp(-r * T), abs=1e-9)


def test_greeks_match_finite_differences():
    S, K, T, r, s = 500, 500, 10 / 365, 0.04, 0.18
    g = bs_greeks(S, K, T, r, s, "C")
    h = 0.01
    delta = (bs_price(S + h, K, T, r, s, "C") - bs_price(S - h, K, T, r, s, "C")) / (2 * h)
    vega = (bs_price(S, K, T, r, s + 0.01, "C") - bs_price(S, K, T, r, s - 0.01, "C")) / 2
    assert g["delta"] == pytest.approx(delta, rel=1e-4)
    assert g["vega"] == pytest.approx(vega, rel=1e-3)
    assert g["theta"] < 0


def test_implied_vol_inverts_price():
    price = bs_price(500, 490, 0.05, 0.04, 0.27, "P")
    assert implied_vol(price, 500, 490, 0.05, 0.04, "P") == pytest.approx(0.27, abs=1e-5)
    assert implied_vol(0.0, 500, 490, 0.05, 0.04, "P") is None


def test_skew_raises_downside_vol():
    T = 1 / 365
    assert skewed_iv(0.15, 500, 490, T) > 0.15 > skewed_iv(0.15, 500, 510, T)


def test_zero_dte_time_floor_and_expiries():
    late = datetime(2024, 3, 15, 15, 59, 30, tzinfo=ET)
    assert year_fraction(late, date(2024, 3, 15)) > 0
    exp = list_expiries(date(2024, 3, 13), 30)  # Wednesday
    assert exp[0] == date(2024, 3, 13)
    assert all(d.weekday() < 5 for d in exp)
    assert all(d.weekday() == 4 for d in exp if (d - date(2024, 3, 13)).days > 7)


def test_vix_proxy_and_real_bar_preference():
    now = datetime(2024, 3, 15, 10, 0, tzinfo=ET)
    spec = OptionSpec("SPY", date(2024, 3, 15), "C", 500)
    real_bar = Bar(now - timedelta(minutes=1), 1.5, 1.6, 1.4, 1.55)
    pricer = OptionPricer(
        iv_lookup=lambda idx, d: 20.0 if idx == "VIX" else None,
        real_lookup=lambda sym, at: real_bar if sym == spec.symbol and at >= real_bar.ts else None,
    )
    assert pricer.atm_iv("SPY", now.date()) == pytest.approx(0.18)
    q = pricer.quote(spec, 500, now)
    assert q.source == "real" and q.price == 1.55
    other = pricer.quote(OptionSpec("SPY", date(2024, 3, 15), "P", 500), 500, now)
    assert other.source == "model" and other.price > 0


def test_model_option_bar_moves_with_underlying():
    pricer = OptionPricer()
    ts = datetime(2024, 3, 15, 10, 0, tzinfo=ET)
    under = Bar(ts, 500, 502, 499, 501)
    call, src = pricer.option_bar("SPY240315C00500000", under)
    put, _ = pricer.option_bar("SPY240315P00500000", under)
    assert src == "model"
    assert call.high > call.low and put.high > put.low
    assert call.close > call.open and put.close < put.open
