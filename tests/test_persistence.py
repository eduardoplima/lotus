"""Shared ingestion persistence: idempotency + provenance (§6.3)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from db.models import OhlcBar
from ingestion.persistence import NormalizedBar, get_or_create_instrument, store_bars
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_BAR = NormalizedBar(
    ts=dt.datetime(2026, 6, 1, tzinfo=dt.UTC),
    open=Decimal("100.123456789012"),
    high=Decimal("101"),
    low=Decimal("99"),
    close=Decimal("100.5"),
    volume=Decimal("12.5"),
)


async def test_get_or_create_is_idempotent(session: AsyncSession) -> None:
    a = await get_or_create_instrument(
        session, "btcusdt", sec_type="CRYPTO", exchange="BINANCE", currency="USDT"
    )
    b = await get_or_create_instrument(
        session, "BTCUSDT", sec_type="CRYPTO", exchange="BINANCE", currency="USDT"
    )
    assert a.id == b.id and a.symbol == "BTCUSDT"


async def test_same_symbol_different_sec_type_is_distinct(session: AsyncSession) -> None:
    spot = await get_or_create_instrument(
        session, "BTC", sec_type="CRYPTO", exchange="BINANCE", currency="USDT"
    )
    perp = await get_or_create_instrument(
        session, "BTC", sec_type="PERP", exchange="HYPERLIQUID", currency="USDC"
    )
    assert spot.id != perp.id


async def test_store_bars_idempotent_rerun(session: AsyncSession) -> None:
    inst = await get_or_create_instrument(
        session, "BTCUSDT", sec_type="CRYPTO", exchange="BINANCE", currency="USDT"
    )
    first = await store_bars(
        session, inst, [_BAR], timeframe="1h", source="BINANCE", vintage="2026-07-03"
    )
    await session.commit()
    second = await store_bars(
        session, inst, [_BAR], timeframe="1h", source="BINANCE", vintage="2026-07-04"
    )
    assert (first, second) == (1, 0)  # re-run inserts nothing, restates nothing

    row = await session.scalar(select(OhlcBar).where(OhlcBar.instrument_id == inst.id))
    assert row.vintage == "2026-07-03"  # original vintage untouched
    assert row.source == "BINANCE"
