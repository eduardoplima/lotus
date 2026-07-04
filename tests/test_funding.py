"""Funding-rate schema + persistence (§6.3, §6.4)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from db.models import FundingRate
from ingestion.persistence import (
    NormalizedFundingRate,
    get_or_create_instrument,
    store_funding_rates,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

_TS = dt.datetime(2026, 7, 1, 12, tzinfo=dt.UTC)


async def _perp(session: AsyncSession):
    return await get_or_create_instrument(
        session, "BTC", sec_type="PERP", exchange="HYPERLIQUID", currency="USDC"
    )


async def test_duplicate_funding_rejected_by_schema(session: AsyncSession) -> None:
    inst = await _perp(session)
    for _ in range(2):
        session.add(
            FundingRate(
                instrument_id=inst.id,
                ts=_TS,
                rate=Decimal("0.0000125"),
                source="HYPERLIQUID",
                vintage="2026-07-03",
            )
        )
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_store_funding_idempotent(session: AsyncSession) -> None:
    inst = await _perp(session)
    rates = [
        NormalizedFundingRate(ts=_TS, rate=Decimal("0.0000125"), premium=Decimal("0.0001")),
        NormalizedFundingRate(
            ts=_TS + dt.timedelta(hours=1), rate=Decimal("-0.0000030"), premium=None
        ),
    ]
    first = await store_funding_rates(
        session, inst, rates, source="HYPERLIQUID", vintage="2026-07-03"
    )
    await session.commit()
    second = await store_funding_rates(
        session, inst, rates, source="HYPERLIQUID", vintage="2026-07-03"
    )
    assert (first, second) == (2, 0)
