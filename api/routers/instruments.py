"""Instrument listing (read-only)."""

from __future__ import annotations

from db.models import Instrument
from fastapi import APIRouter
from sqlalchemy import select

from api.deps import SessionDep
from api.schemas import InstrumentOut

router = APIRouter(tags=["instruments"])


@router.get("/instruments", response_model=list[InstrumentOut])
async def list_instruments(session: SessionDep) -> list[Instrument]:
    result = await session.scalars(select(Instrument).order_by(Instrument.symbol))
    return list(result.all())
