"""Pre-registration discipline + failure cemetery (§7.1/§7.2)."""

from __future__ import annotations

import pytest
from backtest.hypotheses import (
    PreRegistrationError,
    kill_hypothesis,
    list_cemetery,
    register_hypothesis,
)
from db.models import HypothesisStatus
from sqlalchemy.ext.asyncio import AsyncSession

_VALID = {
    "statement": "MES intraday SMA-cross beats always-long after costs",
    "baseline": "always-long 1 MES contract over the same window",
    "signal_threshold": "fast=10/slow=30 frozen on 2026-H1 dev split",
    "dev_split_def": "dev = 2026-01..2026-03, test = 2026-04..2026-06",
    "kill_test": "does edge survive on the highest-vol week (weakest assumption)",
    "kill_criteria": "killed if test-split Sharpe < 0 or max_dd < -5%",
}


async def test_register_requires_all_four_fields(session: AsyncSession) -> None:
    for missing in ("baseline", "kill_test", "kill_criteria", "signal_threshold"):
        bad = dict(_VALID, **{missing: "  "})
        with pytest.raises(PreRegistrationError):
            await register_hypothesis(session, **bad)


async def test_register_then_kill_moves_to_cemetery(session: AsyncSession) -> None:
    hyp = await register_hypothesis(session, **_VALID)
    assert hyp.status == HypothesisStatus.REGISTERED

    killed = await kill_hypothesis(session, hyp.id, reason="test-split Sharpe was -0.4")
    assert killed.status == HypothesisStatus.KILLED
    assert killed.killed_at is not None
    assert killed.kill_reason == "test-split Sharpe was -0.4"

    cemetery = await list_cemetery(session)
    assert [h.id for h in cemetery] == [hyp.id]  # killed → recorded, not deleted
