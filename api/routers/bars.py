"""Historical OHLC bars for one instrument (read-only).

Point-in-time honest: bars are returned exactly as captured, ordered by their
own timestamp. No restating, no forward-fill (§6.2/§6.3).
"""

from __future__ import annotations

from db.models import Instrument, OhlcBar
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from api.deps import SessionDep
from api.schemas import OhlcBarOut

router = APIRouter(tags=["bars"])


@router.get("/instruments/{symbol}/bars", response_model=list[OhlcBarOut])
async def get_bars(
    symbol: str,
    session: SessionDep,
    timeframe: str = Query(default="1d"),
    limit: int = Query(default=500, ge=1, le=5000),
) -> list[OhlcBar]:
    instrument = await session.scalar(select(Instrument).where(Instrument.symbol == symbol.upper()))
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"Unknown instrument: {symbol}")

    result = await session.scalars(
        select(OhlcBar)
        .where(OhlcBar.instrument_id == instrument.id, OhlcBar.timeframe == timeframe)
        .order_by(OhlcBar.ts)
        .limit(limit)
    )
    return list(result.all())
