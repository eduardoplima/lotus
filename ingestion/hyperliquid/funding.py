"""Ingest Hyperliquid perp funding-rate history into Postgres (§6.3, §6.4).

Unlike candles (5000-cap), fundingHistory paginates back to the coin's
inception — full funding history is retrievable and is a first-class cost
input for any perp backtest. Hourly accrual, one row per hour.
"""

from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from ingestion.hyperliquid.client import HyperliquidClient
from ingestion.persistence import (
    EmptyDataError,
    NormalizedFundingRate,
    get_or_create_instrument,
    store_funding_rates,
    today_vintage,
)

logger = logging.getLogger("lotus.ingestion.hyperliquid")

SOURCE = "HYPERLIQUID"


def _normalize(row: dict) -> NormalizedFundingRate:
    """fundingHistory row {coin, fundingRate, premium, time} — strings → Decimal."""
    premium = row.get("premium")
    return NormalizedFundingRate(
        ts=dt.datetime.fromtimestamp(int(row["time"]) / 1000, tz=dt.UTC),
        rate=Decimal(row["fundingRate"]),
        premium=Decimal(premium) if premium is not None else None,
    )


async def ingest_funding(
    session: AsyncSession,
    coin: str,
    start: dt.datetime,
    end: dt.datetime | None = None,
) -> int:
    """Backfill funding history. Idempotent; returns rows inserted."""
    end = end or dt.datetime.now(tz=dt.UTC)

    async with HyperliquidClient() as client:
        await client.validate_coin(coin)
        raw = await client.fetch_funding_history(
            coin, int(start.timestamp() * 1000), int(end.timestamp() * 1000)
        )

    if not raw:
        raise EmptyDataError(
            f"Hyperliquid returned no funding history for {coin!r} in "
            f"{start.date()}..{end.date()}. Recording the gap, not filling it."
        )

    instrument = await get_or_create_instrument(
        session, coin, sec_type="PERP", exchange="HYPERLIQUID", currency="USDC"
    )
    inserted = await store_funding_rates(
        session,
        instrument,
        [_normalize(r) for r in raw],
        source=SOURCE,
        vintage=today_vintage(),
    )
    await session.commit()
    logger.info("Ingested %s funding: %s new rows (of %s returned)", coin, inserted, len(raw))
    return inserted
