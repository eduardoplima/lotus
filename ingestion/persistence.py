"""Source-agnostic persistence for ingested market data (§6.3).

The integrity invariants live here, written once: every stored datum carries
source + captured_at + non-null vintage; stores are insert-only and idempotent
(existing timestamps are skipped, never restated); empty results raise instead
of silently recording nothing. Each source package (ibkr, binance, hyperliquid)
normalizes its wire format into the dataclasses below and delegates.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from db.models import FundingRate, Instrument, OhlcBar
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class EmptyDataError(RuntimeError):
    """A source returned no data — a hole to record, not to fill (§6.3)."""


@dataclass(frozen=True, slots=True)
class NormalizedBar:
    """One OHLC bar in canonical form. `ts` is the bar OPEN time, tz-aware UTC.

    Prices/volume are Decimal end-to-end — crypto APIs return strings and must
    never round-trip through float.
    """

    ts: dt.datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None  # base-asset units


@dataclass(frozen=True, slots=True)
class NormalizedFundingRate:
    """One funding accrual. `ts` is the funding time, tz-aware UTC."""

    ts: dt.datetime
    rate: Decimal
    premium: Decimal | None


def today_vintage() -> str:
    """The as-of vintage tag for data captured now (§6.3)."""
    return dt.datetime.now(tz=dt.UTC).date().isoformat()


def _as_utc(ts: dt.datetime) -> dt.datetime:
    """Normalize a DB-read timestamp to tz-aware UTC.

    Postgres returns aware datetimes; SQLite (tests) returns naive ones. The
    skip-existing comparison must not silently miss on that mismatch — a miss
    here would re-insert and violate insert-only idempotency.
    """
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=dt.UTC)


async def get_or_create_instrument(
    session: AsyncSession,
    symbol: str,
    *,
    sec_type: str,
    exchange: str,
    currency: str,
) -> Instrument:
    symbol = symbol.upper()
    instrument = await session.scalar(
        select(Instrument).where(Instrument.symbol == symbol, Instrument.sec_type == sec_type)
    )
    if instrument is None:
        instrument = Instrument(
            symbol=symbol, sec_type=sec_type, exchange=exchange, currency=currency
        )
        session.add(instrument)
        await session.flush()
    return instrument


async def store_bars(
    session: AsyncSession,
    instrument: Instrument,
    bars: Sequence[NormalizedBar],
    *,
    timeframe: str,
    source: str,
    vintage: str,
) -> int:
    """Persist new bars; return count inserted. Insert-only: existing
    (instrument, ts, timeframe) rows are skipped, never restated."""
    existing_ts = {
        _as_utc(ts)
        for ts in await session.scalars(
            select(OhlcBar.ts).where(
                OhlcBar.instrument_id == instrument.id,
                OhlcBar.timeframe == timeframe,
            )
        )
    }
    inserted = 0
    for bar in bars:
        if bar.ts in existing_ts:
            continue
        session.add(
            OhlcBar(
                instrument_id=instrument.id,
                ts=bar.ts,
                timeframe=timeframe,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                source=source,
                vintage=vintage,
            )
        )
        inserted += 1
    return inserted


async def store_funding_rates(
    session: AsyncSession,
    instrument: Instrument,
    rates: Sequence[NormalizedFundingRate],
    *,
    source: str,
    vintage: str,
) -> int:
    """Persist new funding rates; skip existing (instrument, ts). Insert-only."""
    existing_ts = {
        _as_utc(ts)
        for ts in await session.scalars(
            select(FundingRate.ts).where(FundingRate.instrument_id == instrument.id)
        )
    }
    inserted = 0
    for rate in rates:
        if rate.ts in existing_ts:
            continue
        session.add(
            FundingRate(
                instrument_id=instrument.id,
                ts=rate.ts,
                rate=rate.rate,
                premium=rate.premium,
                source=source,
                vintage=vintage,
            )
        )
        inserted += 1
    return inserted
