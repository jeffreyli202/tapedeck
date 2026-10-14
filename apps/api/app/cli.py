"""Run ingestion directly, without the worker.

    python -m app.cli seed --days 20
    python -m app.cli iv
    python -m app.cli bars SPY 2024-03-01 2024-03-31
    python -m app.cli options SPY 2024-03-15
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date

from app.db import engine
from app.services import ingest


async def main() -> None:
    parser = argparse.ArgumentParser(prog="tapedeck")
    sub = parser.add_subparsers(dest="cmd", required=True)
    seed = sub.add_parser("seed", help="generate synthetic SPY/QQQ bars and VIX/VXN levels")
    seed.add_argument("--days", type=int, default=20)
    sub.add_parser("iv", help="download VIX/VXN daily levels")
    bars = sub.add_parser("bars", help="ingest Alpaca 1-minute bars")
    bars.add_argument("symbol")
    bars.add_argument("start", type=date.fromisoformat)
    bars.add_argument("end", type=date.fromisoformat)
    opts = sub.add_parser("options", help="ingest Alpaca option bars for one day")
    opts.add_argument("symbol")
    opts.add_argument("day", type=date.fromisoformat)
    opts.add_argument("--strikes", type=int, default=10)
    args = parser.parse_args()

    if args.cmd == "seed":
        result = await ingest.seed_synthetic(args.days)
    elif args.cmd == "iv":
        result = await ingest.ingest_vol_indices()
    elif args.cmd == "bars":
        result = await ingest.ingest_stock_bars(args.symbol.upper(), args.start, args.end)
    else:
        result = await ingest.ingest_option_day(args.symbol.upper(), args.day, args.strikes)
    print(json.dumps(result, indent=2, default=str))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
