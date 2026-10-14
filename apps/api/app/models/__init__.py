from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

Json = JSON().with_variant(JSONB(), "postgresql")
TS = DateTime(timezone=True)


class BarRow(Base):
    __tablename__ = "bars"
    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    ts: Mapped[datetime] = mapped_column(TS, primary_key=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float, default=0)
    vwap: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(16), default="alpaca")


class OptionContract(Base):
    __tablename__ = "option_contracts"
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    underlying: Mapped[str] = mapped_column(String(16), index=True)
    expiry: Mapped[date] = mapped_column(Date)
    strike: Mapped[float] = mapped_column(Float)
    right: Mapped[str] = mapped_column(String(1))


class OptionBarRow(Base):
    __tablename__ = "option_bars"
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    ts: Mapped[datetime] = mapped_column(TS, primary_key=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float, default=0)
    vwap: Mapped[float | None] = mapped_column(Float)


class IvDaily(Base):
    __tablename__ = "iv_daily"
    index: Mapped[str] = mapped_column(String(8), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float | None] = mapped_column(Float)


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    starting_cash: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class ReplaySession(Base):
    __tablename__ = "replay_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(16))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    cursor_ts: Mapped[datetime | None] = mapped_column(TS)
    speed: Mapped[float] = mapped_column(Float, default=10)
    status: Mapped[str] = mapped_column(String(16), default="paused")
    starting_cash: Mapped[float] = mapped_column(Float)
    engine_state: Mapped[dict | None] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class OrderRow(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("replay_sessions.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(32))
    asset_class: Mapped[str] = mapped_column(String(8))
    side: Mapped[str] = mapped_column(String(4))
    qty: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(8))
    limit_price: Mapped[float | None] = mapped_column(Float)
    stop_price: Mapped[float | None] = mapped_column(Float)
    take_profit: Mapped[float | None] = mapped_column(Float)
    stop_loss: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(10))
    parent_id: Mapped[str | None] = mapped_column(String(32))
    tag: Mapped[str | None] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(Text)
    created_ts: Mapped[datetime | None] = mapped_column(TS)
    filled_ts: Mapped[datetime | None] = mapped_column(TS)
    fill_price: Mapped[float | None] = mapped_column(Float)


class FillRow(Base):
    __tablename__ = "fills"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("replay_sessions.id", ondelete="CASCADE"), index=True)
    order_id: Mapped[str] = mapped_column(String(32))
    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(4))
    qty: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)
    commission: Mapped[float] = mapped_column(Float)
    ts: Mapped[datetime] = mapped_column(TS)
    price_source: Mapped[str] = mapped_column(String(12))


class PositionRow(Base):
    __tablename__ = "positions"
    session_id: Mapped[str] = mapped_column(ForeignKey("replay_sessions.id", ondelete="CASCADE"), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    qty: Mapped[int] = mapped_column(Integer)
    avg_cost: Mapped[float] = mapped_column(Float)
    realized_pnl: Mapped[float] = mapped_column(Float)
    updated_ts: Mapped[datetime | None] = mapped_column(TS)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    strategy: Mapped[str] = mapped_column(String(64))
    symbol: Mapped[str] = mapped_column(String(16))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    starting_cash: Mapped[float] = mapped_column(Float)
    params: Mapped[dict] = mapped_column(Json)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict | None] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(TS)


class TradeRow(Base):
    """A closed round trip, from either a replay session or a backtest."""

    __tablename__ = "backtest_trades"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("backtest_runs.id", ondelete="CASCADE"))
    session_id: Mapped[str | None] = mapped_column(ForeignKey("replay_sessions.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(32))
    direction: Mapped[str] = mapped_column(String(5))
    qty: Mapped[int] = mapped_column(Integer)
    entry_ts: Mapped[datetime] = mapped_column(TS)
    exit_ts: Mapped[datetime] = mapped_column(TS)
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float] = mapped_column(Float)
    pnl: Mapped[float] = mapped_column(Float)
    commission: Mapped[float] = mapped_column(Float)

    __table_args__ = (Index("ix_trades_run", "run_id"), Index("ix_trades_session", "session_id"))


class EquityPointRow(Base):
    __tablename__ = "equity_points"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("backtest_runs.id", ondelete="CASCADE"))
    session_id: Mapped[str | None] = mapped_column(ForeignKey("replay_sessions.id", ondelete="CASCADE"))
    ts: Mapped[datetime] = mapped_column(TS)
    equity: Mapped[float] = mapped_column(Float)
    exposure: Mapped[float] = mapped_column(Float, default=0)

    __table_args__ = (Index("ix_equity_run_ts", "run_id", "ts"), Index("ix_equity_session_ts", "session_id", "ts"))


class JournalNote(Base):
    __tablename__ = "journal_notes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    trade_id: Mapped[int | None] = mapped_column(ForeignKey("backtest_trades.id", ondelete="SET NULL"))
    session_id: Mapped[str | None] = mapped_column(ForeignKey("replay_sessions.id", ondelete="CASCADE"))
    run_id: Mapped[str | None] = mapped_column(ForeignKey("backtest_runs.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(Json, default=list)
    screenshot: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), onupdate=func.now())
