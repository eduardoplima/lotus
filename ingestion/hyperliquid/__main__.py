"""Headless Hyperliquid PERP ingestion entry point.

Usage:
    python -m ingestion.hyperliquid ingest-bars BTC --interval 1h --start 2026-01-01
    python -m ingestion.hyperliquid ingest-funding BTC --start 2024-01-01

Public info API — no auth for market data. NOTE: candles are capped at the
most recent ~5000 per coin+interval; a start before that raises unless
--allow-truncated is passed (explicit operator decision, §6.3).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import logging
import sys

import httpx
from db.session import get_sessionmaker

from ingestion.hyperliquid.bars import TruncatedHistoryError, ingest_bars
from ingestion.hyperliquid.client import UnknownCoinError
from ingestion.hyperliquid.funding import ingest_funding
from ingestion.persistence import EmptyDataError


def _parse_date(s: str) -> dt.datetime:
    return dt.datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=dt.UTC)


async def _run_bars(args: argparse.Namespace) -> int:
    async with get_sessionmaker()() as session:
        return await ingest_bars(
            session,
            args.coin,
            args.interval,
            args.start,
            args.end,
            allow_truncated=args.allow_truncated,
        )


async def _run_funding(args: argparse.Namespace) -> int:
    async with get_sessionmaker()() as session:
        return await ingest_funding(session, args.coin, args.start, args.end)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser(prog="python -m ingestion.hyperliquid")
    sub = parser.add_subparsers(dest="command", required=True)

    p_bars = sub.add_parser("ingest-bars", help="Backfill perp candles into Postgres")
    p_bars.add_argument("coin", help="Perp name, case-sensitive (e.g. BTC)")
    p_bars.add_argument("--interval", default="1h", help="e.g. 1m/1h/1d")
    p_bars.add_argument("--start", type=_parse_date, required=True, help="YYYY-MM-DD (UTC)")
    p_bars.add_argument("--end", type=_parse_date, default=None)
    p_bars.add_argument(
        "--allow-truncated",
        action="store_true",
        help="Accept the available window when the 5000-candle cap truncates history",
    )

    p_fund = sub.add_parser("ingest-funding", help="Backfill funding history into Postgres")
    p_fund.add_argument("coin")
    p_fund.add_argument("--start", type=_parse_date, required=True)
    p_fund.add_argument("--end", type=_parse_date, default=None)

    args = parser.parse_args(argv)

    try:
        if args.command == "ingest-bars":
            inserted = asyncio.run(_run_bars(args))
            print(f"ingested {inserted} new {args.interval} bars for {args.coin}")
        else:
            inserted = asyncio.run(_run_funding(args))
            print(f"ingested {inserted} new funding rows for {args.coin}")
        return 0
    except (EmptyDataError, TruncatedHistoryError, UnknownCoinError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (httpx.HTTPError, OSError, TimeoutError) as exc:
        print(f"error: Hyperliquid request failed ({exc}).", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
