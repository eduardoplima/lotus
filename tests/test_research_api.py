"""Read-only research API: registry, cemetery, runs/results (§10)."""

from __future__ import annotations

from backtest.hypotheses import kill_hypothesis, register_hypothesis
from db.models import BacktestResult, BacktestRun
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

_VALID = {
    "statement": "S",
    "baseline": "B",
    "signal_threshold": "T",
    "dev_split_def": "D",
    "kill_test": "K",
    "kill_criteria": "C",
}


async def test_cemetery_endpoint_lists_only_killed(
    client: AsyncClient, session: AsyncSession
) -> None:
    alive = await register_hypothesis(session, **dict(_VALID, statement="alive"))
    dead = await register_hypothesis(session, **dict(_VALID, statement="dead"))
    await kill_hypothesis(session, dead.id, reason="failed kill test")
    await session.commit()

    all_res = await client.get("/api/hypotheses")
    assert {h["statement"] for h in all_res.json()} == {"alive", "dead"}

    cem = await client.get("/api/cemetery")
    ids = [h["id"] for h in cem.json()]
    assert ids == [dead.id] and alive.id not in ids


async def test_run_result_roundtrip(client: AsyncClient, session: AsyncSession) -> None:
    run = BacktestRun(
        hypothesis_id=None,
        strategy="sma_cross",
        params={"fast": 10, "slow": 30},
        data_window={"symbol": "MES", "n_bars": 232},
        cost_model={"commission_per_contract_usd": 1.0},
        code_version="abc123",
        config_hash="deadbeef",
    )
    session.add(run)
    await session.flush()
    session.add(
        BacktestResult(
            run_id=run.id,
            headline={"total_positions": 5},
            stress_windows={"covid_2020": "not_covered"},
            tail={"max_drawdown_frac": -0.0033},
        )
    )
    await session.commit()

    res = await client.get(f"/api/backtest-runs/{run.id}/result")
    assert res.status_code == 200
    body = res.json()
    assert body["tail"]["max_drawdown_frac"] == -0.0033
    assert body["headline"]["total_positions"] == 5
