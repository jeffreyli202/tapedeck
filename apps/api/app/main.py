from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.config import settings
from app.core.fill_engine import OrderRejected
from app.db import engine
from app.routers import analytics, auth, backtests, data, journal, sessions
from app.services.replay import ReplayError, ReplayManager
from app.ws import routes as ws_routes

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.arq = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    app.state.replay = ReplayManager(app.state.redis)
    yield
    await app.state.replay.shutdown()
    await app.state.arq.aclose()
    await app.state.redis.aclose()
    await engine.dispose()


app = FastAPI(title="TapeDeck API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ReplayError)
@app.exception_handler(OrderRejected)
async def domain_error(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


for r in (auth.router, sessions.router, backtests.router, analytics.router, journal.router, data.router):
    app.include_router(r)
app.include_router(ws_routes.router)
