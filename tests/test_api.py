"""API endpoint tests over the in-memory DB."""

from __future__ import annotations

import datetime as dt

from db.models import Instrument, OhlcBar
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def test_health(client: AsyncClient) -> None:
    res = await client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


async def test_meta_exposes_assumption(client: AsyncClient) -> None:
    res = await client.get("/api/meta")
    assert res.status_code == 200
    body = res.json()
    assert body["gex_is_assumption_dependent"] is True
    assert "dealer_sign_convention" in body


async def test_bars_roundtrip(client: AsyncClient, session: AsyncSession) -> None:
    inst = Instrument(symbol="SPY", sec_type="STK", exchange="SMART", currency="USD")
    session.add(inst)
    await session.flush()
    session.add(
        OhlcBar(
            instrument_id=inst.id,
            ts=dt.datetime(2026, 6, 1, tzinfo=dt.UTC),
            timeframe="1d",
            open=100,
            high=105,
            low=99,
            close=103,
            volume=1_000_000,
            source="IBKR",
            vintage="2026-06-01",
        )
    )
    await session.commit()

    res = await client.get("/api/instruments/SPY/bars?timeframe=1d")
    assert res.status_code == 200
    bars = res.json()
    assert len(bars) == 1
    assert bars[0]["close"] == 103.0
    assert bars[0]["source"] == "IBKR"


async def test_bars_unknown_symbol_404(client: AsyncClient) -> None:
    res = await client.get("/api/instruments/NOPE/bars")
    assert res.status_code == 404
