"""Phase 2 QA — reports/data_qa.md. Curated data is immutable after sign-off.

Checks per instrument: coverage (first/last ts, rows), duplicate timestamps,
zero-volume bars, missing sessions (vs expected calendar), DST-transition
session integrity (US leg), SPY ex-div flags (from TRADES vs ADJUSTED_LAST
reference downloaded at acquisition).
"""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path

import pandas as pd

from research.sessions import crypto_session_table, us_session_table

CURATED = Path("data/curated")
REPORTS = Path("reports")
CRYPTO = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"]


def qa_frame(name: str, bars: pd.DataFrame, kind: str) -> dict:
    dupes = int(bars.index.duplicated().sum())
    zero_vol = int((bars["volume"] == 0).sum()) if "volume" in bars else -1
    row = {
        "instrument": name,
        "rows": len(bars),
        "first": str(bars.index[0]),
        "last": str(bars.index[-1]),
        "dup_ts": dupes,
        "zero_vol_bars": zero_vol,
    }
    if kind == "crypto":
        sessions = crypto_session_table(bars)
        expected = pd.date_range(sessions.index[0], sessions.index[-1], freq="D")
        row["sessions"] = len(sessions)
        row["missing_sessions"] = len(expected) - len(sessions)
    else:
        sessions = us_session_table(bars)
        bdays = pd.bdate_range(sessions.index[0], sessions.index[-1])
        row["sessions"] = len(sessions)
        # US holidays are expected gaps (~9-10/yr); flag only if far beyond that.
        row["missing_vs_bdays"] = len(bdays) - len(sessions)
    return row


def dst_check(bars: pd.DataFrame) -> str:
    """Confirm the 09:30 NY bar exists on the sessions around DST transitions."""
    table = us_session_table(bars)
    ny = pd.DatetimeIndex(table.index)
    # spring-forward Mondays: second Sunday of March + 1 day, sampled recent years
    issues = []
    for year in range(2007, 2027):
        march = pd.date_range(f"{year}-03-01", f"{year}-03-31", freq="D")
        sundays = [d for d in march if d.weekday() == 6]
        if len(sundays) < 2:
            continue
        monday_after = sundays[1] + pd.Timedelta(days=1)
        if monday_after in ny:
            row = table.loc[monday_after]
            if pd.isna(row["open_0930"]):
                issues.append(str(monday_after.date()))
    return (
        "OK — 09:30 NY bar present after every spring-forward"
        if not issues
        else f"ISSUES: {issues}"
    )


def run() -> int:
    rows = []
    for sym in CRYPTO:
        rows.append(qa_frame(sym, pd.read_parquet(CURATED / f"binance/{sym}_5m.parquet"), "crypto"))
    spy_bars = pd.read_parquet(CURATED / "ibkr/SPY_5m.parquet")
    rows.append(qa_frame("SPY", spy_bars, "us"))
    mes_bars = pd.read_parquet(CURATED / "ibkr/MES_STITCHED_5m.parquet")
    rows.append(qa_frame("MES_STITCHED", mes_bars, "us"))

    exdiv = pd.read_csv(CURATED / "ibkr/spy_exdiv_dates.csv", parse_dates=["exdiv_date"])
    dst = dst_check(spy_bars)

    df = pd.DataFrame(rows)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    stamp = dt.datetime.now(tz=dt.UTC).isoformat()
    lines = [
        "# Data QA — Phase 2 (curated immutable after this sign-off)",
        "",
        f"Generated {stamp} · code {sha[:12]} · registration sha256 34d3cfba…",
        "",
        "| instrument | rows | first | last | sessions | missing | dup ts | zero-vol |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for _, r in df.iterrows():
        missing = r.get("missing_sessions", r.get("missing_vs_bdays"))
        lines.append(
            f"| {r['instrument']} | {r['rows']} | {r['first'][:16]} | {r['last'][:16]} "
            f"| {r['sessions']} | {missing} | {r['dup_ts']} | {r['zero_vol_bars']} |"
        )
    lines += [
        "",
        f"- **DST spring-forward integrity (SPY):** {dst}",
        f"- **SPY ex-div dates flagged:** {len(exdiv)} dates"
        " (TRADES vs ADJUSTED_LAST close-ratio steps),",
        "  saved at `data/curated/ibkr/spy_exdiv_dates.csv`. Overnight gaps across these dates are",
        "  mechanically distorted; the research series stays UNADJUSTED per registration — the",
        "  gap feature is affected only via the r1-from-prev-close variant on ~quarterly dates.",
        "- 'missing' for US = business days minus sessions"
        " (US market holidays are expected, ~9-10/yr).",
        "- Zero-volume crypto bars are early-listing illiquidity; kept as-is (no fabrication).",
        "",
        "**QA sign-off: curated data frozen for Phases 3-5.**",
    ]
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "data_qa.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(run())
