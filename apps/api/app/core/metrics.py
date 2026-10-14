"""Performance statistics for both replay sessions and backtests."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from app.core.types import et

TRADING_DAYS = 252
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]


@dataclass
class EquityPoint:
    ts: datetime
    equity: float
    exposure: float = 0.0


@dataclass
class TradeRecord:
    pnl: float
    entry_ts: datetime
    exit_ts: datetime
    direction: str = "long"


def drawdown_series(points: list[EquityPoint]) -> list[dict]:
    peak = -math.inf
    out = []
    for p in points:
        peak = max(peak, p.equity)
        out.append({"t": int(p.ts.timestamp()), "dd": p.equity / peak - 1 if peak > 0 else 0.0})
    return out


def _max_drawdown(points: list[EquityPoint]) -> tuple[float, float]:
    """Largest peak-to-trough decline (as a negative fraction) and the longest
    time spent below a prior peak, in seconds."""
    peak = -math.inf
    peak_ts = None
    underwater = False
    max_dd = 0.0
    longest = 0.0
    for p in points:
        if p.equity >= peak:
            if underwater:
                longest = max(longest, (p.ts - peak_ts).total_seconds())
            peak, peak_ts, underwater = p.equity, p.ts, False
            continue
        underwater = True
        max_dd = min(max_dd, p.equity / peak - 1)
    if underwater:
        longest = max(longest, (points[-1].ts - peak_ts).total_seconds())
    return max_dd, longest


def daily_returns(points: list[EquityPoint], starting_equity: float) -> np.ndarray:
    closes: dict = {}
    for p in points:
        closes[et(p.ts).date()] = p.equity
    series = np.array([starting_equity, *closes.values()], dtype=float)
    return series[1:] / series[:-1] - 1 if len(series) > 1 else np.array([])


def compute_metrics(
    points: list[EquityPoint], trades: list[TradeRecord], starting_equity: float
) -> dict:
    final = points[-1].equity if points else starting_equity
    total_return = final / starting_equity - 1
    span_days = (points[-1].ts - points[0].ts).total_seconds() / 86400 if len(points) > 1 else 0
    cagr = None
    if span_days >= 1 and final > 0:
        cagr = (final / starting_equity) ** (365.25 / span_days) - 1

    rets = daily_returns(points, starting_equity)
    sharpe = sortino = None
    if len(rets) >= 2 and rets.std(ddof=1) > 0:
        sharpe = float(rets.mean() / rets.std(ddof=1) * math.sqrt(TRADING_DAYS))
        downside = rets[rets < 0]
        if len(downside) >= 2 and downside.std(ddof=1) > 0:
            sortino = float(rets.mean() / downside.std(ddof=1) * math.sqrt(TRADING_DAYS))

    max_dd, dd_secs = _max_drawdown(points)
    pnls = np.array([t.pnl for t in trades], dtype=float)
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    gross_win, gross_loss = float(wins.sum()), float(-losses.sum())

    return {
        "starting_equity": starting_equity,
        "final_equity": final,
        "net_pnl": final - starting_equity,
        "total_return": total_return,
        "cagr": cagr,
        "max_drawdown": max_dd,
        "max_drawdown_duration_s": dd_secs,
        "sharpe": sharpe,
        "sortino": sortino,
        "trades": len(trades),
        "win_rate": float(len(wins) / len(pnls)) if len(pnls) else None,
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else None,
        "expectancy": float(pnls.mean()) if len(pnls) else None,
        "avg_win": float(wins.mean()) if len(wins) else None,
        "avg_loss": float(losses.mean()) if len(losses) else None,
        "largest_win": float(pnls.max()) if len(pnls) else None,
        "largest_loss": float(pnls.min()) if len(pnls) else None,
        "exposure": float(np.mean([p.exposure > 0 for p in points])) if points else 0.0,
        "trading_days": len(rets),
    }


def _bucket(ts: datetime) -> str:
    local = et(ts)
    minute = 30 * (local.minute // 30)
    return f"{local.hour:02d}:{minute:02d}"


def by_time_of_day(trades: list[TradeRecord]) -> list[dict]:
    groups: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        groups[_bucket(t.entry_ts)].append(t.pnl)
    return [_group_stats(k, v) for k, v in sorted(groups.items())]


def by_weekday(trades: list[TradeRecord]) -> list[dict]:
    groups: dict[int, list[float]] = defaultdict(list)
    for t in trades:
        groups[et(t.entry_ts).weekday()].append(t.pnl)
    return [_group_stats(WEEKDAYS[k], groups[k]) for k in range(5) if k in groups]


def heatmap(trades: list[TradeRecord]) -> list[dict]:
    """P&L by weekday x 30-minute entry bucket."""
    cells: dict[tuple[int, str], list[float]] = defaultdict(list)
    for t in trades:
        cells[(et(t.entry_ts).weekday(), _bucket(t.entry_ts))].append(t.pnl)
    return [
        {"weekday": WEEKDAYS[wd], "bucket": b, "pnl": sum(v), "count": len(v)}
        for (wd, b), v in sorted(cells.items())
        if wd < 5
    ]


def histogram(trades: list[TradeRecord], bins: int = 20) -> list[dict]:
    if not trades:
        return []
    pnls = np.array([t.pnl for t in trades], dtype=float)
    lo, hi = float(pnls.min()), float(pnls.max())
    if lo == hi:
        lo, hi = lo - 1, hi + 1
    counts, edges = np.histogram(pnls, bins=bins, range=(lo, hi))
    return [
        {"from": float(edges[i]), "to": float(edges[i + 1]), "count": int(c)}
        for i, c in enumerate(counts)
    ]


def _group_stats(key: str, pnls: list[float]) -> dict:
    wins = sum(1 for p in pnls if p > 0)
    return {"key": key, "pnl": sum(pnls), "count": len(pnls), "win_rate": wins / len(pnls)}
