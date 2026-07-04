"""Hypothesis pre-registration registry + failure cemetery (§7.1/§7.2).

A hypothesis is not valid until pre-registered with all four fields *before* the
test data is touched (§7.1). Killed hypotheses are moved to `killed` status and
never deleted — that set is the failure cemetery (§7.2), the visible denominator
of the multiple-testing count.
"""

from __future__ import annotations

import datetime as dt

from db.models import Hypothesis, HypothesisStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Mandatory stress windows for the equity/index track (§7.4). Other tracks
# define their own asset-appropriate windows. A strategy tested only on benign
# data is not tested.
STRESS_WINDOWS: dict[str, tuple[str, str]] = {
    "volmageddon_2018": ("2018-02-01", "2018-02-28"),
    "covid_2020": ("2020-02-20", "2020-04-30"),
    "rate_bear_2022": ("2022-01-01", "2022-10-31"),
    "vol_spike_2024_08": ("2024-07-25", "2024-08-15"),
}


class PreRegistrationError(ValueError):
    """Raised when a hypothesis is missing a required §7.1 field."""


async def register_hypothesis(
    session: AsyncSession,
    *,
    statement: str,
    baseline: str,
    signal_threshold: str,
    dev_split_def: str,
    kill_test: str,
    kill_criteria: str,
) -> Hypothesis:
    """Pre-register a hypothesis (§7.1). All four discipline fields are required.

    `baseline` is the comparative claim against an unconditional benchmark;
    `signal_threshold` must be frozen ex-ante on the dev split; `kill_test` is the
    single most falsifying test; `kill_criteria` are the numeric death conditions.
    """
    fields = {
        "statement": statement,
        "baseline": baseline,
        "signal_threshold": signal_threshold,
        "dev_split_def": dev_split_def,
        "kill_test": kill_test,
        "kill_criteria": kill_criteria,
    }
    missing = [k for k, v in fields.items() if not v or not v.strip()]
    if missing:
        raise PreRegistrationError(
            f"cannot register hypothesis — missing required §7.1 field(s): {', '.join(missing)}"
        )

    hyp = Hypothesis(status=HypothesisStatus.REGISTERED, **fields)
    session.add(hyp)
    await session.flush()
    return hyp


async def kill_hypothesis(session: AsyncSession, hypothesis_id: int, reason: str) -> Hypothesis:
    """Move a hypothesis to the cemetery (§7.2). Never deletes."""
    hyp = await session.get(Hypothesis, hypothesis_id)
    if hyp is None:
        raise ValueError(f"no hypothesis with id={hypothesis_id}")
    hyp.status = HypothesisStatus.KILLED
    hyp.killed_at = dt.datetime.now(tz=dt.UTC)
    hyp.kill_reason = reason
    await session.flush()
    return hyp


async def list_cemetery(session: AsyncSession) -> list[Hypothesis]:
    """All killed hypotheses — the multiple-testing denominator (§7.2)."""
    result = await session.scalars(
        select(Hypothesis).where(Hypothesis.status == HypothesisStatus.KILLED)
    )
    return list(result.all())
