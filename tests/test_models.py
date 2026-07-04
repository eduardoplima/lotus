"""Schema-level integrity checks (§6.3)."""

from __future__ import annotations

import datetime as dt

import pytest
from db.models import Instrument, OhlcBar
from ingestion.ibkr.bars import TIMEFRAME_DAILY
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


async def _spy(session: AsyncSession) -> Instrument:
    inst = Instrument(symbol="SPY", sec_type="STK", exchange="SMART", currency="USD")
    session.add(inst)
    await session.flush()
    return inst


def _bar(inst: Instrument, ts: dt.datetime) -> OhlcBar:
    return OhlcBar(
        instrument_id=inst.id,
        ts=ts,
        timeframe=TIMEFRAME_DAILY,
        open=100,
        high=101,
        low=99,
        close=100.5,
        volume=1000,
        source="IBKR",
        vintage="2026-06-01",
    )


async def test_duplicate_bar_rejected(session: AsyncSession) -> None:
    inst = await _spy(session)
    ts = dt.datetime(2026, 6, 1, tzinfo=dt.UTC)
    session.add(_bar(inst, ts))
    await session.commit()

    session.add(_bar(inst, ts))  # same (instrument, ts, timeframe)
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_captured_at_autopopulated(session: AsyncSession) -> None:
    inst = await _spy(session)
    bar = _bar(inst, dt.datetime(2026, 6, 2, tzinfo=dt.UTC))
    session.add(bar)
    await session.commit()
    await session.refresh(bar)
    assert bar.captured_at is not None
