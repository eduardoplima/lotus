"""Historical OHLC bars for one instrument (read-only).

Point-in-time honest: bars are returned exactly as captured, ordered by their
own timestamp. No restating, no forward-fill (§6.2/§6.3).
"""

from __future__ import annotations

from db.models import FundingRate, Instrument, OhlcBar
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from api.deps import SessionDep
from api.schemas import FundingRateOut, OhlcBarOut

router = APIRouter(tags=["bars"])


async def _instrument_or_404(session, symbol: str) -> Instrument:
    instrument = await session.scalar(
        select(Instrument).where(Instrument.symbol == symbol.upper())
    )
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"Unknown instrument: {symbol}")
    return instrument


@router.get("/instruments/{symbol}/bars", response_model=list[OhlcBarOut])
async def get_bars(
    symbol: str,
    session: SessionDep,
    timeframe: str = Query(default="1d"),
    limit: int = Query(default=500, ge=1, le=5000),
) -> list[OhlcBar]:
    instrument = await _instrument_or_404(session, symbol)
    # Most-recent window: take the LAST `limit` bars, returned in ascending
    # order (what a chart consumes).
    result = await session.scalars(
        select(OhlcBar)
        .where(OhlcBar.instrument_id == instrument.id, OhlcBar.timeframe == timeframe)
        .order_by(OhlcBar.ts.desc())
        .limit(limit)
    )
    return list(reversed(result.all()))


@router.get("/instruments/{symbol}/funding", response_model=list[FundingRateOut])
async def get_funding(
    symbol: str,
    session: SessionDep,
    limit: int = Query(default=1000, ge=1, le=10000),
) -> list[FundingRate]:
    """Perp funding-rate history (read-only), ascending, most-recent window."""
    instrument = await _instrument_or_404(session, symbol)
    result = await session.scalars(
        select(FundingRate)
        .where(FundingRate.instrument_id == instrument.id)
        .order_by(FundingRate.ts.desc())
        .limit(limit)
    )
    return list(reversed(result.all()))
