"""Acquire MES per-expiry 5m bars and build the stitched research series.

WHY THIS EXISTS (constraint reported, not hidden): IB rejects paged historical
requests for continuous futures — Error 10339 verbatim: "Setting end date/time
for continuous future security type is not allowed." So the CONTFUT path from
the registration cannot page beyond one request. Per the registration's own
fallback, the research series is instead STITCHED from per-expiry contracts
with a VOLUME-BASED ROLL; per-contract series are kept for the Nautilus leg.

Expired-futures caveat: IB serves expired futures history for a limited window
(~2 years). Contracts whose data is gone come back empty — recorded as holes,
which SHORTENS the MES sample. The actual coverage is reported, never padded.

Per-expiry contract: Future(..., includeExpired=True) — verified in installed
ib_async 2.1.0. Pacing: 11s sleeps (same doc-verified budget as acquire_ibkr).
Run AFTER acquire_ibkr.py finishes (shared pacing budget).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import os
import sys
from pathlib import Path

import pandas as pd
from ib_async import IB, Future

from research.acquire_ibkr import PACING_SLEEP_S, bars_to_frame

logger = logging.getLogger("lotus.research.acquire_mes")

RAW = Path("data/raw/ibkr/MES_EXPIRIES")
CURATED = Path("data/curated/ibkr")

# Quarterly expiries potentially covering 2023-06 → 2026-09. Old ones may be
# beyond IB's expired-data window — empty results are recorded as holes.
CONTRACT_MONTHS = [
    "202309", "202312", "202403", "202406", "202409", "202412",
    "202503", "202506", "202509", "202512", "202603", "202606", "202609",
]


def _life_window(cm: str) -> tuple[dt.date, dt.date]:
    """Fetch window per contract: from ~4 months before its month to month end."""
    y, m = int(cm[:4]), int(cm[4:])
    end_y, end_m = (y + 1, 1) if m == 12 else (y, m + 1)
    start_m = m - 4
    start_y = y
    if start_m <= 0:
        start_m += 12
        start_y -= 1
    return dt.date(start_y, start_m, 1), dt.date(end_y, end_m, 1)


async def fetch_contract(ib: IB, cm: str) -> int:
    outdir = RAW / cm
    outdir.mkdir(parents=True, exist_ok=True)
    contract = Future(
        symbol="MES", exchange="CME", lastTradeDateOrContractMonth=cm, includeExpired=True
    )
    qualified = await ib.qualifyContractsAsync(contract)
    if not qualified:
        logger.warning("MES %s: cannot qualify (beyond expired-data window) — hole recorded", cm)
        (outdir / "UNAVAILABLE").write_text("could not qualify contract\n")
        return 0

    start, end = _life_window(cm)
    total = 0
    cursor = start
    while cursor < end:
        nxt_y, nxt_m = (
            (cursor.year + 1, 1) if cursor.month == 12 else (cursor.year, cursor.month + 1)
        )
        nxt = min(dt.date(nxt_y, nxt_m, 1), end)
        dest = outdir / f"{cursor:%Y-%m}.parquet"
        if not dest.exists():
            bars = await ib.reqHistoricalDataAsync(
                contract,
                endDateTime=dt.datetime(nxt.year, nxt.month, nxt.day, tzinfo=dt.UTC),
                durationStr="1 M",
                barSizeSetting="5 mins",
                whatToShow="TRADES",
                useRTH=False,
            )
            df = bars_to_frame(bars)
            if df.empty:
                dest.with_suffix(".EMPTY").write_text("no bars\n")
            else:
                df.to_parquet(dest)
                total += len(df)
                logger.info("MES %s %s: %d bars", cm, f"{cursor:%Y-%m}", len(df))
            await asyncio.sleep(PACING_SLEEP_S)
        cursor = nxt
    return total


def stitch_research_series() -> dict:
    """Volume-based roll: per UTC day, use the contract with the highest volume;
    once rolled forward, never roll back."""
    per_contract: dict[str, pd.DataFrame] = {}
    for cm in CONTRACT_MONTHS:
        chunks = sorted((RAW / cm).glob("*.parquet"))
        if not chunks:
            continue
        df = pd.concat([pd.read_parquet(p) for p in chunks])
        df = df[~df.index.duplicated(keep="first")].sort_index()
        per_contract[cm] = df
        df.to_parquet(CURATED / f"MES_{cm}_5m.parquet")  # per-contract series (Nautilus leg)

    if not per_contract:
        raise RuntimeError("no MES expiry data at all — hole recorded, sprint MES leg is blocked")

    daily_vol = pd.DataFrame(
        {cm: df["volume"].groupby(df.index.date).sum() for cm, df in per_contract.items()}
    ).fillna(0.0)
    order = {cm: i for i, cm in enumerate(CONTRACT_MONTHS)}
    front, last_idx = {}, -1
    for day, row in daily_vol.iterrows():
        best = row.idxmax()
        if row[best] <= 0:
            continue
        # never roll backward
        if order[best] < last_idx:
            best = CONTRACT_MONTHS[last_idx]
        last_idx = max(last_idx, order[best])
        front[day] = best

    pieces = []
    for cm, df in per_contract.items():
        days = {d for d, c in front.items() if c == cm}
        sel = df[pd.Index(df.index.date).isin(days)]
        if not sel.empty:
            pieces.append(sel.assign(contract=cm))
    stitched = pd.concat(pieces).sort_index()
    stitched.to_parquet(CURATED / "MES_STITCHED_5m.parquet")
    return {
        "contracts_with_data": sorted(per_contract),
        "rows": len(stitched),
        "first": str(stitched.index[0]),
        "last": str(stitched.index[-1]),
    }


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    CURATED.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240 — one-shot script
    ib = IB()
    await ib.connectAsync(
        host=os.environ.get("IB_HOST", "127.0.0.1"),
        port=int(os.environ.get("IB_PORT", "4001")),
        clientId=int(os.environ.get("IB_CLIENT_ID", "44")),
        timeout=15,
    )
    for cm in CONTRACT_MONTHS:
        await fetch_contract(ib, cm)
    ib.disconnect()
    print("STITCHED", stitch_research_series(), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
