from datetime import date

import pytest

from app.core.fill_engine import FillConfig, FillEngine, Order, OrderStatus, OrderType, Position, Side
from app.core.occ import occ_symbol
from tests.conftest import T0, make_bar

NO_FRICTION = FillConfig(stock_slippage_bps=0, option_slippage_pct=0, option_min_slippage=0,
                         option_commission_per_contract=0)


def engine(cash=100_000.0, config=NO_FRICTION) -> FillEngine:
    e = FillEngine(cash, config)
    e.last_prices["SPY"] = 500.0
    return e


def test_market_order_fills_on_next_bar_open_not_signal_bar():
    e = engine()
    o = e.submit(Order("SPY", Side.BUY, 10), make_bar(0, 500, 501, 499, 500.5).ts)
    assert e.on_bar("SPY", make_bar(0, 500, 501, 499, 500.5)) == []
    fills = e.on_bar("SPY", make_bar(1, 502, 503, 501, 502.5))
    assert len(fills) == 1 and fills[0].price == 502
    assert o.status == OrderStatus.FILLED
    assert e.cash == pytest.approx(100_000 - 5020)


def test_limit_requires_trade_through_and_fills_at_open_on_gap():
    e = engine()
    o = e.submit(Order("SPY", Side.BUY, 1, OrderType.LIMIT, limit_price=499), T0)
    e.on_bar("SPY", make_bar(1, 500, 501, 499, 500))  # touches but does not trade through
    assert o.status == OrderStatus.OPEN
    e.on_bar("SPY", make_bar(2, 500, 500, 498.5, 499))
    assert o.fill_price == 499

    o2 = e.submit(Order("SPY", Side.BUY, 1, OrderType.LIMIT, limit_price=499), make_bar(2, 0, 0, 0, 0).ts)
    e.on_bar("SPY", make_bar(3, 497, 498, 496, 497))  # gaps below the limit: better fill
    assert o2.fill_price == 497


def test_stop_order_with_slippage():
    e = engine(config=FillConfig(stock_slippage_bps=10))
    o = e.submit(Order("SPY", Side.SELL, 1, OrderType.STOP, stop_price=495), T0)
    e.on_bar("SPY", make_bar(1, 500, 500, 494, 495))
    assert o.fill_price == pytest.approx(495 * (1 - 0.001))


def test_bracket_spawns_oco_legs_and_stop_wins_ambiguous_bar():
    e = engine()
    e.submit(Order("SPY", Side.BUY, 10, take_profit=505, stop_loss=495), T0)
    e.on_bar("SPY", make_bar(1, 500, 501, 499, 500))
    legs = [o for o in e.open_orders() if o.parent_id]
    assert {o.tag for o in legs} == {"take_profit", "stop_loss"}
    # Both target and stop trade in the same bar: assume the stop hit first.
    e.on_bar("SPY", make_bar(2, 500, 506, 494, 500))
    statuses = {o.tag: o.status for o in legs}
    assert statuses == {"take_profit": OrderStatus.CANCELED, "stop_loss": OrderStatus.FILLED}
    assert e.position_qty("SPY") == 0
    assert e.closed_trades[-1].pnl == pytest.approx(-50)


def test_round_trip_pnl_includes_commissions_and_flips():
    e = engine(config=FillConfig(stock_slippage_bps=0, stock_commission_per_share=0.01))
    e.submit(Order("SPY", Side.BUY, 100), T0)
    e.on_bar("SPY", make_bar(1, 500, 500, 500, 500))
    e.submit(Order("SPY", Side.SELL, 150), make_bar(1, 0, 0, 0, 0).ts)
    e.on_bar("SPY", make_bar(2, 501, 501, 501, 501))
    assert e.position_qty("SPY") == -50
    t = e.closed_trades[0]
    # 100 * $1 gross, minus $1 entry and 100/150 of the $1.50 exit commission
    assert t.pnl == pytest.approx(100 - 1 - 1.0)
    assert e.positions["SPY"].avg_cost == 501


def test_buying_power_rejects_oversized_orders():
    e = engine(cash=1_000)
    o = e.submit(Order("SPY", Side.BUY, 10), T0)
    assert o.status == OrderStatus.REJECTED and "buying power" in o.reason
    short = engine(cash=1_000)
    short.positions["SPY"] = Position("SPY", qty=-10, avg_cost=500)
    assert short.submit(Order("SPY", Side.BUY, 10), T0).status == OrderStatus.OPEN, "closing is always allowed"


def test_option_expiry_settles_at_intrinsic():
    e = engine()
    sym = occ_symbol("SPY", date(2024, 3, 15), "C", 500)
    e.last_prices[sym] = 2.0
    e.submit(Order(sym, Side.BUY, 2), T0)
    e.on_bar(sym, make_bar(1, 2.0, 2.1, 1.9, 2.0))
    assert e.cash == pytest.approx(100_000 - 400)
    e.last_prices["SPY"] = 503.5
    fills = e.settle_expiries(date(2024, 3, 15), make_bar(390, 0, 0, 0, 0).ts)
    assert fills[0].price == pytest.approx(3.5) and fills[0].price_source == "settlement"
    assert e.position_qty(sym) == 0
    assert e.cash == pytest.approx(100_000 - 400 + 700)


def test_state_round_trips_through_dict():
    e = engine()
    e.submit(Order("SPY", Side.BUY, 10, take_profit=510, stop_loss=490), T0)
    e.on_bar("SPY", make_bar(1, 500, 501, 499, 500))
    clone = FillEngine.from_dict(e.to_dict())
    assert clone.cash == e.cash
    assert clone.position_qty("SPY") == 10
    assert {o.tag for o in clone.open_orders()} == {"take_profit", "stop_loss"}
