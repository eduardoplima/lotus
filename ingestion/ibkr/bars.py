"""Ingest daily OHLC bars from IBKR into Postgres.

Integrity (§6.3): we fail loudly on an empty result rather than inventing a
bar; existing bars are never restated (insert-only via ingestion.persistence),
so re-running is idempotent and point-in-time honest.
"""

from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from ingestion.ibkr.ib_client import IBClient
from ingestion.persistence import (
    EmptyDataError,
    NormalizedBar,
    store_bars,
    today_vintage,
)
from ingestion.persistence import (
    get_or_create_instrument as _get_or_create,
)

logger = logging.getLogger("lotus.ingestion.bars")

TIMEFRAME_DAILY = "1d"


class EmptyBarsError(EmptyDataError):
    """Raised when IBKR returns no bars — a hole to record, not to fill."""


def _to_utc_datetime(value: dt.date | dt.datetime) -> dt.datetime:
    if isinstance(value, dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt.UTC)
    return dt.datetime(value.year, value.month, value.day, tzinfo=dt.UTC)


async def get_or_create_instrument(session: AsyncSession, symbol: str):
    return await _get_or_create(
        session, symbol, sec_type="STK", exchange="SMART", currency="USD"
    )


def _normalize(bar) -> NormalizedBar:
    volume = (
        Decimal(str(bar.volume)) if bar.volume is not None and bar.volume >= 0 else None
    )
    return NormalizedBar(
        ts=_to_utc_datetime(bar.date),
        open=Decimal(str(bar.open)),
        high=Decimal(str(bar.high)),
        low=Decimal(str(bar.low)),
        close=Decimal(str(bar.close)),
        volume=volume,
    )


async def store_daily_bars(session: AsyncSession, instrument, raw_bars) -> int:
    """Persist new daily bars; return count inserted. Skips timestamps already stored."""
    return await store_bars(
        session,
        instrument,
        [_normalize(bar) for bar in raw_bars],
        timeframe=TIMEFRAME_DAILY,
        source="IBKR",
        vintage=today_vintage(),
    )


async def ingest_daily_bars(session: AsyncSession, symbol: str, duration: str = "1 Y") -> int:
    """End-to-end ingest: pull daily bars from IBKR and persist them.

    Requires a reachable IB Gateway/TWS. Returns the number of new bars
    inserted. Raises EmptyBarsError if IBKR returns nothing.
    """
    async with IBClient() as client:
        raw_bars = await client.fetch_daily_bars(symbol, duration=duration)

    if not raw_bars:
        raise EmptyBarsError(
            f"IBKR returned no daily bars for {symbol!r}. Recording the gap, not filling it."
        )

    instrument = await get_or_create_instrument(session, symbol)
    inserted = await store_daily_bars(session, instrument, raw_bars)
    await session.commit()
    logger.info("Ingested %s: %s new bars (of %s returned)", symbol, inserted, len(raw_bars))
    return inserted
