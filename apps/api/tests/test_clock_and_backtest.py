from datetime import date

import pytest

from app.core.clock import ClockStatus, ReplayClock
from app.core.fill_engine import FillEngine
from app.core.pricer import OptionPricer
from app.core.strategies import STRATEGIES, build_strategy
from app.core.strategy import Backtester
from app.data.synthetic import generate, weekdays_back


@pytest.fixture(scope="module")
def bars():
    days = weekdays_back(date(2024, 3, 15), 5)
    return generate("SPY", days)[0]


def test_clock_reveals_only_up_to_cursor(bars):
    clock = ReplayClock(bars, speed=60)
    assert len(clock.visible()) == 1
    assert clock.interval_seconds == 1
    nxt = clock.advance()
    assert clock.visible()[-1] is nxt and len(clock.visible()) == 2
    assert clock.index_at(bars[100].ts) == 100
    assert clock.is_day_end(389) and not clock.is_day_end(388)
    clock.index = len(bars) - 2
    clock.advance()
    assert clock.status == ClockStatus.FINISHED and clock.advance() is None
    clock.set_speed(1000)
    assert clock.speed == 60


@pytest.mark.parametrize("name", list(STRATEGIES))
def test_builtin_strategies_run_and_end_flat(bars, name):
    strategy = build_strategy(name, {})
    engine = FillEngine(100_000)
    result = Backtester(strategy, "SPY", bars, engine, OptionPricer()).run()
    assert len(result.equity) == len(bars)
    assert result.metrics["final_equity"] == pytest.approx(engine.equity())
    if strategy.p.flatten_eod:
        assert not [p for p in engine.open_positions()], "flatten_eod should leave no overnight positions"
        assert not [f for f in result.fills if f.price_source == "settlement"], "exits should fill before expiry"
    if name != "ma_crossover":
        assert result.metrics["trades"] > 0


def test_param_schema_is_exposed():
    schema = STRATEGIES["orb"].schema()
    props = schema["params"]["properties"]
    assert props["range_minutes"]["default"] == 15
    assert "flatten_eod" in props
