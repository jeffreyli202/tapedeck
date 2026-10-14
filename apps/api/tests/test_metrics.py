from datetime import datetime, timedelta

import pytest

from app.core.metrics import (
    EquityPoint,
    TradeRecord,
    by_weekday,
    compute_metrics,
    drawdown_series,
    heatmap,
    histogram,
)
from app.core.types import ET

D0 = datetime(2024, 3, 11, 16, 0, tzinfo=ET)  # a Monday close


def curve(values):
    return [EquityPoint(D0 + timedelta(days=i), v, 1.0 if i % 2 else 0.0) for i, v in enumerate(values)]


def test_drawdown_and_duration():
    pts = curve([100, 110, 99, 105, 120, 108])
    m = compute_metrics(pts, [], 100)
    assert m["max_drawdown"] == pytest.approx(99 / 110 - 1)
    assert m["max_drawdown_duration_s"] == pytest.approx(3 * 86400)  # 110 on day 1, recovered day 4
    dd = drawdown_series(pts)
    assert dd[1]["dd"] == 0 and dd[2]["dd"] < 0
    assert m["total_return"] == pytest.approx(0.08)


def test_trade_stats():
    t0 = datetime(2024, 3, 11, 9, 45, tzinfo=ET)
    trades = [TradeRecord(p, t0, t0 + timedelta(minutes=5)) for p in (100, -50, 200, -50)]
    m = compute_metrics(curve([100_000, 100_200]), trades, 100_000)
    assert m["win_rate"] == 0.5
    assert m["profit_factor"] == pytest.approx(3.0)
    assert m["expectancy"] == pytest.approx(50)
    assert m["avg_win"] == 150 and m["avg_loss"] == -50
    assert by_weekday(trades)[0]["key"] == "Mon"
    assert heatmap(trades)[0]["bucket"] == "09:30"
    assert sum(b["count"] for b in histogram(trades, 5)) == 4


def test_sharpe_sign_and_no_trades():
    up = compute_metrics(curve([100, 101, 102.5, 103, 104.2]), [], 100)
    assert up["sharpe"] > 0
    flat = compute_metrics(curve([100, 100, 100]), [], 100)
    assert flat["sharpe"] is None and flat["win_rate"] is None
