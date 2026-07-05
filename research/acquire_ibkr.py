"""Acquire IBKR historical 5m bars for the sprint (Phase 2): SPY + MES continuous.

Per the approved registration: SPY 5-min TRADES useRTH from 2005-01-01; MES via
ContFuture (research series) from its head timestamp 2023-06-18. Chunked monthly
requests, resumable (one raw Parquet per month; existing chunks are skipped).

Pacing — verified against the official TWS API docs
(https://interactivebrokers.github.io/tws-api/historical_limitations.html):
  * no more than 60 historical requests within any ten-minute period;
  * no identical requests within 15 seconds;
  * <=6 requests for the same contract within two seconds.
We sleep 11s between requests (~54 per 10 min) — conservative and compliant.

Ex-dividend detection for QA: two extra daily-bar requests (TRADES and
ADJUSTED_LAST, 21 years each — both verified `whatToShow` values in the TWS
docs). Dates where the adjusted/unadjusted close ratio steps are ex-div dates;
they are saved for the QA report. The research series itself stays UNADJUSTED
TRADES, as registered.

API names verified against installed ib_async 2.1.0 (rule 7): connectAsync,
qualifyContractsAsync, reqHistoricalDataAsync, Stock, ContFuture.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import os
import sys
from pathlib import Path

import pandas as pd
from ib_async import IB, ContFuture, Stock

logger = logging.getLogger("lotus.research.acquire_ibkr")

RAW = Path("data/raw/ibkr")
CURATED = Path("data/curated/ibkr")
PACING_SLEEP_S = 11.0  # ~54 req / 10 min < 60 (see module docstring)

SPY_START = dt.date(2005, 1, 1)
MES_START = dt.date(2023, 6, 18)  # head timestamp from preflight
END = dt.date(2026, 6, 30)  # holdout end per registration


def month_ends(start: dt.date, end: dt.date):
    """Yield (label, endDateTime) month chunks covering [start, end]."""
    y, m = start.year, start.month
    while dt.date(y, m, 1) <= end:
        nm_y, nm_m = (y + 1, 1) if m == 12 else (y, m + 1)
        chunk_end = min(dt.date(nm_y, nm_m, 1), end + dt.timedelta(days=1))
        yield (
            f"{y:04d}-{m:02d}",
            dt.datetime(chunk_end.year, chunk_end.month, chunk_end.day, tzinfo=dt.UTC),
        )
        y, m = nm_y, nm_m


def bars_to_frame(bars) -> pd.DataFrame:
    rows = [
        {
            "ts": b.date,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": float(b.volume) if b.volume is not None else None,
        }
        for b in bars
    ]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.set_index("ts").sort_index()


async def fetch_months(ib: IB, contract, label: str, start: dt.date, use_rth: bool) -> None:
    outdir = RAW / label
    outdir.mkdir(parents=True, exist_ok=True)
    for month, end_dt in month_ends(start, END):
        dest = outdir / f"{month}.parquet"
        if dest.exists():
            continue  # resumable
        bars = await ib.reqHistoricalDataAsync(
            contract,
            endDateTime=end_dt,
            durationStr="1 M",
            barSizeSetting="5 mins",
            whatToShow="TRADES",
            useRTH=use_rth,
        )
        df = bars_to_frame(bars)
        if df.empty:
            # Record the hole explicitly; never fabricate (§6.3).
            logger.warning("%s %s: empty month", label, month)
            dest.with_suffix(".EMPTY").write_text("no bars returned\n")
        else:
            # Trim to the month (requests overlap at boundaries).
            df = df[df.index < pd.Timestamp(end_dt)]
            df.to_parquet(dest)
            logger.info("%s %s: %d bars", label, month, len(df))
        await asyncio.sleep(PACING_SLEEP_S)


def consolidate(label: str, out_name: str) -> dict:
    chunks = sorted((RAW / label).glob("*.parquet"))
    if not chunks:
        # A hole, recorded loudly — e.g. CONTFUT paging is rejected by IB
        # (Error 10339 verbatim); MES research data comes from acquire_mes.py.
        return {"label": label, "chunks": 0, "note": "no data — hole recorded"}
    df = pd.concat([pd.read_parquet(p) for p in chunks])
    df = df[~df.index.duplicated(keep="first")].sort_index()
    CURATED.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CURATED / out_name)
    return {
        "label": label,
        "chunks": len(chunks),
        "rows": len(df),
        "first": str(df.index[0]),
        "last": str(df.index[-1]),
    }


async def fetch_exdiv_reference(ib: IB, spy) -> None:
    """Daily TRADES vs ADJUSTED_LAST closes → ex-div dates for QA."""
    frames = {}
    for what in ("TRADES", "ADJUSTED_LAST"):
        bars = await ib.reqHistoricalDataAsync(
            spy,
            endDateTime="",
            durationStr="21 Y",
            barSizeSetting="1 day",
            whatToShow=what,
            useRTH=True,
        )
        frames[what] = pd.Series({pd.Timestamp(b.date): b.close for b in bars}, name=what.lower())
        await asyncio.sleep(PACING_SLEEP_S)
    both = pd.concat(frames.values(), axis=1).dropna()
    ratio = (both["adjusted_last"] / both["trades"]).round(8)
    # A real SPY dividend is ~0.2-0.5% of price → ratio step ~2e-3..5e-3.
    # Cent-rounding noise moves the ratio by ~1e-5 daily; threshold 5e-4
    # separates the two regimes cleanly (~4 events/yr expected).
    exdiv = ratio[ratio.diff().abs() > 5e-4].index
    out = CURATED / "spy_exdiv_dates.csv"
    pd.Series(exdiv, name="exdiv_date").to_csv(out, index=False)
    logger.info("ex-div reference: %d dates -> %s", len(exdiv), out)


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    CURATED.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240 — one-shot script
    host = os.environ.get("IB_HOST", "127.0.0.1")
    port = int(os.environ.get("IB_PORT", "4001"))
    client_id = int(os.environ.get("IB_CLIENT_ID", "43"))

    ib = IB()
    await ib.connectAsync(host=host, port=port, clientId=client_id, timeout=15)
    spy = Stock("SPY", "SMART", "USD")
    mes = ContFuture("MES", "CME")
    await ib.qualifyContractsAsync(spy, mes)

    await fetch_exdiv_reference(ib, spy)
    await fetch_months(ib, mes, "MES_CONT", MES_START, use_rth=False)
    await fetch_months(ib, spy, "SPY", SPY_START, use_rth=True)
    ib.disconnect()

    print("CONSOLIDATED", consolidate("SPY", "SPY_5m.parquet"), flush=True)
    print("CONSOLIDATED", consolidate("MES_CONT", "MES_CONT_5m.parquet"), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
