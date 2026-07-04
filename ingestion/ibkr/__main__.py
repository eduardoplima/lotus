"""Headless IBKR ingestion entry point (M0/M1 live path).

Usage:
    python -m ingestion.ibkr ingest SPY [--duration "1 Y"]

Requires a reachable IB Gateway/TWS — see .env for IB_HOST/IB_PORT. This is the
live ib_async ingestion path into Postgres; the backtest catalog is populated
separately by `python -m backtest.download_ib` (nautilus IB adapter).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from core.config import settings
from db.session import get_sessionmaker

from ingestion.ibkr.bars import EmptyBarsError, ingest_daily_bars


async def _run_ingest(symbol: str, duration: str) -> int:
    async with get_sessionmaker()() as session:
        return await ingest_daily_bars(session, symbol, duration=duration)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser(prog="python -m ingestion.ibkr")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Pull daily bars for a symbol from IBKR")
    p_ingest.add_argument("symbol")
    p_ingest.add_argument("--duration", default="1 Y", help='IB durationStr, e.g. "1 Y"')

    args = parser.parse_args(argv)

    if args.command == "ingest":
        try:
            inserted = asyncio.run(_run_ingest(args.symbol, args.duration))
        except EmptyBarsError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        except (OSError, TimeoutError) as exc:
            # Gateway not reachable is an expected operational condition.
            print(
                f"error: could not reach IB Gateway/TWS at "
                f"{settings.ib_host}:{settings.ib_port} ({exc}).\n"
                f"hint: start a Gateway/TWS and enable its API, or set "
                f"IB_HOST/IB_PORT in .env (Gateway live=4001, paper=4002).",
                file=sys.stderr,
            )
            return 3
        print(f"ingested {inserted} new daily bars for {args.symbol.upper()}")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
