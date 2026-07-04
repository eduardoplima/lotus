"""Headless Binance SPOT ingestion entry point.

Usage:
    python -m ingestion.binance ingest BTCUSDT --interval 1d --start 2024-01-01

Public REST — no API key needed for market data. Binance geo-blocks restricted
IPs with HTTP 451 (this host is in Brazil — fine).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import logging
import sys

import httpx
from db.session import get_sessionmaker

from ingestion.binance.bars import ingest_bars
from ingestion.binance.client import BinanceBannedError, BinanceGeoBlockedError
from ingestion.persistence import EmptyDataError


def _parse_date(s: str) -> dt.datetime:
    return dt.datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=dt.UTC)


async def _run(symbol: str, interval: str, start: dt.datetime, end: dt.datetime | None) -> int:
    async with get_sessionmaker()() as session:
        return await ingest_bars(session, symbol, interval, start, end)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser(prog="python -m ingestion.binance")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", help="Backfill spot klines for a symbol into Postgres")
    p.add_argument("symbol")
    p.add_argument("--interval", default="1d", help="Binance interval, e.g. 1m/1h/1d")
    p.add_argument("--start", type=_parse_date, required=True, help="YYYY-MM-DD (UTC)")
    p.add_argument("--end", type=_parse_date, default=None, help="YYYY-MM-DD (default: now)")

    args = parser.parse_args(argv)

    try:
        inserted = asyncio.run(_run(args.symbol, args.interval, args.start, args.end))
    except EmptyDataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (BinanceGeoBlockedError, BinanceBannedError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except (httpx.HTTPError, OSError, TimeoutError) as exc:
        print(f"error: Binance request failed ({exc}).", file=sys.stderr)
        return 3

    print(f"ingested {inserted} new {args.interval} bars for {args.symbol.upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
