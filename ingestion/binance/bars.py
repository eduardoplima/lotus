"""Ingest Binance SPOT klines into Postgres with provenance (§6.3).

Integrity: the in-progress kline (closeTime in the future) is dropped — the
store is insert-only and must never need to restate a bar that was still
forming when captured. Empty results raise; gaps are recorded, not filled.
"""

from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from ingestion.binance.client import BinanceClient
from ingestion.persistence import (
    EmptyDataError,
    NormalizedBar,
    get_or_create_instrument,
    store_bars,
    today_vintage,
)

logger = logging.getLogger("lotus.ingestion.binance")

SOURCE = "BINANCE"


def _normalize(kline: list) -> NormalizedBar:
    """Kline row: [openTime, o, h, l, c, volume, closeTime, ...] — strings → Decimal."""
    return NormalizedBar(
        ts=dt.datetime.fromtimestamp(int(kline[0]) / 1000, tz=dt.UTC),
        open=Decimal(kline[1]),
        high=Decimal(kline[2]),
        low=Decimal(kline[3]),
        close=Decimal(kline[4]),
        volume=Decimal(kline[5]),
    )


def _drop_in_progress(klines: list[list], now_ms: int) -> list[list]:
    """Drop klines whose closeTime is still in the future (§6.3: no restating)."""
    closed = [k for k in klines if int(k[6]) < now_ms]
    dropped = len(klines) - len(closed)
    if dropped:
        logger.info("dropped %s in-progress kline(s) — will land after close", dropped)
    return closed


async def ingest_bars(
    session: AsyncSession,
    symbol: str,
    interval: str,
    start: dt.datetime,
    end: dt.datetime | None = None,
) -> int:
    """Backfill/gap-fill Binance spot bars. Idempotent; returns bars inserted."""
    end = end or dt.datetime.now(tz=dt.UTC)
    now_ms = int(dt.datetime.now(tz=dt.UTC).timestamp() * 1000)

    async with BinanceClient() as client:
        info = await client.fetch_exchange_info(symbol)
        raw = await client.fetch_klines_range(
            symbol,
            interval,
            start_ms=int(start.timestamp() * 1000),
            end_ms=int(end.timestamp() * 1000),
        )

    raw = _drop_in_progress(raw, now_ms)
    if not raw:
        raise EmptyDataError(
            f"Binance returned no closed {interval} klines for {symbol!r} in "
            f"{start.date()}..{end.date()}. Recording the gap, not filling it."
        )

    instrument = await get_or_create_instrument(
        session,
        symbol,
        sec_type="CRYPTO",
        exchange="BINANCE",
        currency=info["quoteAsset"],
    )
    inserted = await store_bars(
        session,
        instrument,
        [_normalize(k) for k in raw],
        timeframe=interval,
        source=SOURCE,
        vintage=today_vintage(),
    )
    await session.commit()
    logger.info(
        "Ingested %s %s: %s new bars (of %s closed returned)",
        symbol,
        interval,
        inserted,
        len(raw),
    )
    return inserted
