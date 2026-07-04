"""Pydantic v2 response schemas.

GEX/wall payloads MUST carry the dealer-sign convention used and the
`assumption_dependent: true` marker (§6.1/§10) — these are modeled numbers,
not measured facts, and the API refuses to let them look authoritative.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InstrumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    sec_type: str
    exchange: str
    currency: str
    multiplier: int
    conid: int | None = None


class OhlcBarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts: datetime
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    source: str
    captured_at: datetime
    vintage: str


class HypothesisOut(BaseModel):
    """A pre-registered hypothesis or a cemetery (killed) entry (§7.1/§7.2)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    statement: str
    baseline: str
    signal_threshold: str
    dev_split_def: str
    kill_test: str
    kill_criteria: str
    status: str
    registered_at: datetime
    killed_at: datetime | None = None
    kill_reason: str | None = None


class BacktestRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hypothesis_id: int | None = None
    strategy: str
    params: dict
    data_window: dict
    cost_model: dict
    code_version: str
    created_at: datetime


class BacktestResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    headline: dict
    stress_windows: dict
    tail: dict
    equity_curve_ref: str | None = None
    computed_at: datetime


class GexSnapshotOut(BaseModel):
    """Served at M2. Present now so the assumption contract is fixed from day one."""

    model_config = ConfigDict(from_attributes=True)

    snapshot_id: int
    dealer_sign_convention: str
    # Always true: every value here depends on an assumed dealer convention.
    assumption_dependent: bool = True
    profile: dict
    call_wall: float | None = None
    put_wall: float | None = None
    computed_at: datetime
