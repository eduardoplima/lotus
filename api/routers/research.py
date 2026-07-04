"""Read-only research endpoints: the hypothesis registry, the failure cemetery,
and backtest runs/results (§7, §10).

Serving these makes the multiple-testing accounting visible: the cemetery is the
denominator of "how many things did we try" (§7.2). Everything here is read-only;
registration/kill happen through the backtest.hypotheses layer, never the API.
"""

from __future__ import annotations

from db.models import BacktestResult, BacktestRun, Hypothesis, HypothesisStatus
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from api.deps import SessionDep
from api.schemas import BacktestResultOut, BacktestRunOut, HypothesisOut

router = APIRouter(tags=["research"])


@router.get("/hypotheses", response_model=list[HypothesisOut])
async def list_hypotheses(
    session: SessionDep,
    status: str | None = Query(default=None, description="filter: registered|live|killed"),
) -> list[Hypothesis]:
    stmt = select(Hypothesis).order_by(Hypothesis.registered_at.desc())
    if status is not None:
        stmt = stmt.where(Hypothesis.status == status)
    return list(await session.scalars(stmt))


@router.get("/cemetery", response_model=list[HypothesisOut])
async def cemetery(session: SessionDep) -> list[Hypothesis]:
    """Killed hypotheses only — the multiple-testing denominator (§7.2)."""
    stmt = select(Hypothesis).where(Hypothesis.status == HypothesisStatus.KILLED)
    return list(await session.scalars(stmt))


@router.get("/backtest-runs", response_model=list[BacktestRunOut])
async def list_runs(session: SessionDep) -> list[BacktestRun]:
    stmt = select(BacktestRun).order_by(BacktestRun.created_at.desc())
    return list(await session.scalars(stmt))


@router.get("/backtest-runs/{run_id}/result", response_model=BacktestResultOut)
async def run_result(run_id: int, session: SessionDep) -> BacktestResult:
    result = await session.scalar(select(BacktestResult).where(BacktestResult.run_id == run_id))
    if result is None:
        raise HTTPException(status_code=404, detail=f"No result for run {run_id}")
    return result
