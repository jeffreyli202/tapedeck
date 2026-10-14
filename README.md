# TapeDeck

Rewind the market. Trade it again.

Paper-trade SPY/QQQ (and their options) against a bar-by-bar replay of a historical session, then backtest the same strategies on the same fill engine.

## Run it

Postgres (Timescale) and Redis should already be up from `docker compose`. Then, in three terminals:

```powershell
# 1. API  (from apps/api, with the venv activated)
.\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000

# 2. Worker
.\.venv\Scripts\arq.exe app.workers.worker.WorkerSettings

# 3. Web  (from apps/web)
npx next dev
```

Open [http://localhost:3000](http://localhost:3000). Synthetic SPY/QQQ bars for the last ~30 weekdays are already loaded, so you can start a replay immediately.

To regenerate synthetic data:

```powershell
cd apps/api
.\.venv\Scripts\python.exe -m app.cli seed --days 30
```

To ingest real Alpaca bars, copy `.env.example` to `.env`, add keys, then use the **Market data** panel on the home page (or `python -m app.cli bars SPY 2024-03-01 2024-03-31`).

## Layout

```
apps/api/app/core/     replay clock, fill engine, option pricer, metrics, strategies
apps/api/app/data/     Alpaca, CBOE/FRED IV, synthetic generator, Timescale store
apps/api/app/services/ replay runtime, backtest runner, ingestion jobs
apps/web/src/app/      replay, backtest, analytics, journal pages
infra/                 Docker Compose (Timescale, Redis, optional full stack)
```

Paper trading and backtests share `FillEngine`. The replay clock lives on the server so the client cannot look ahead.
