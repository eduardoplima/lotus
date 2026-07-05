"""Phase 3 — R1 replication gate (dev split only; vectorized pandas).

Regress last-30-min return on first-30-min return per instrument:
  * SPY: BOTH r1 variants (from previous RTH close [canonical pending human
    confirmation]; from same-day open).
  * Crypto: single variant (24/7).
Report OLS beta, HAC (Newey-West) t, sign hit rate, per-year stability
→ reports/r1_replication.md. The gate is applied mechanically:
expected sign (+) AND HAC t ≥ 2 on dev, for SPY and for BTCUSDT AND ETHUSDT.

Registration sha256 34d3cfba… — parameters frozen; this script takes no knobs.
"""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path

import pandas as pd

from research.sessions import crypto_session_table, us_session_table
from research.stats import ols_hac

CURATED = Path("data/curated")
REPORTS = Path("reports")
DEV_END = pd.Timestamp("2025-07-01")  # dev = strictly before (registration §4)

CRYPTO = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"]
GATE_REQUIRED = {"SPY (from prev close)", "SPY (from open)", "BTCUSDT", "ETHUSDT"}
# Gate rule: SPY passes if the CANONICAL variant (prev close) passes; the other
# variant is reported for completeness. BTC and ETH must both pass.


def _dev(table: pd.DataFrame) -> pd.DataFrame:
    return table[table.index < DEV_END]


def _yearly(table: pd.DataFrame, x_col: str) -> pd.DataFrame:
    rows = []
    for year, grp in table.groupby(table.index.year):
        if len(grp) < 60:
            continue
        try:
            r = ols_hac(grp[x_col].to_numpy(float), grp["last30_ret"].to_numpy(float))
            rows.append({"year": year, "n": r.n, "beta": r.beta, "t_hac": r.t_hac})
        except ValueError:
            continue
    return pd.DataFrame(rows)


def run() -> int:
    results, yearly_blocks = [], []

    spy = us_session_table(pd.read_parquet(CURATED / "ibkr/SPY_5m.parquet"))
    spy_dev = _dev(spy)
    for label, col in (
        ("SPY (from prev close)", "r1_from_prev_close"),
        ("SPY (from open)", "r1_from_open"),
    ):
        r = ols_hac(spy_dev[col].to_numpy(float), spy_dev["last30_ret"].to_numpy(float))
        results.append({"instrument": label, **r.__dict__})
        yb = _yearly(spy_dev, col)
        yb.insert(0, "instrument", label)
        yearly_blocks.append(yb)

    for sym in CRYPTO:
        table = crypto_session_table(pd.read_parquet(CURATED / f"binance/{sym}_5m.parquet"))
        tdev = _dev(table)
        r = ols_hac(tdev["r1_from_open"].to_numpy(float), tdev["last30_ret"].to_numpy(float))
        results.append({"instrument": sym, **r.__dict__})
        yb = _yearly(tdev, "r1_from_open")
        yb.insert(0, "instrument", sym)
        yearly_blocks.append(yb)

    df = pd.DataFrame(results)
    df["pass"] = (df["beta"] > 0) & (df["t_hac"] >= 2.0)

    gate_rows = df[df["instrument"].isin(["SPY (from prev close)", "BTCUSDT", "ETHUSDT"])]
    gate_pass = bool(gate_rows["pass"].all())

    sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    stamp = dt.datetime.now(tz=dt.UTC).isoformat()
    REPORTS.mkdir(exist_ok=True)
    lines = [
        "# R1 Replication Gate — dev split",
        "",
        f"Generated {stamp} · code {sha[:12]} · registration sha256"
        f" 34d3cfba… · dev < {DEV_END.date()}",
        "",
        "Regression: last-30-min return ~ first-30-min return. Expected sign: positive.",
        "Published magnitudes for comparison: **not provided** (papers not"
        " supplied; nothing fabricated).",
        "",
        "| instrument | n | beta | HAC t | lags | hit rate | pass (sign & t≥2) |",
        "|---|---|---|---|---|---|---|",
    ]
    for _, r in df.iterrows():
        lines.append(
            f"| {r['instrument']} | {r['n']} | {r['beta']:.4f} | {r['t_hac']:.2f} "
            f"| {r['lags']} | {r['hit_rate']:.3f} | {'PASS' if r['pass'] else 'FAIL'} |"
        )
    lines += ["", "## Per-year stability", ""]
    ally = pd.concat(yearly_blocks, ignore_index=True)
    lines.append("| instrument | year | n | beta | HAC t |")
    lines.append("|---|---|---|---|---|")
    for _, r in ally.iterrows():
        lines.append(
            f"| {r['instrument']} | {int(r['year'])} | {int(r['n'])} "
            f"| {r['beta']:.4f} | {r['t_hac']:.2f} |"
        )
    lines += [
        "",
        "## Gate verdict (mechanical)",
        "",
        "Required: SPY canonical (prev-close) AND BTCUSDT AND ETHUSDT — sign>0, HAC t≥2.",
        "",
        "**R1 GATE: "
        + ("PASS — proceed to Phase 4" if gate_pass else "FAIL — cemetery entry, sprint ends")
        + "**",
    ]
    (REPORTS / "r1_replication.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[-3:]))
    print(f"report: {REPORTS / 'r1_replication.md'}")
    return 0 if gate_pass else 1


if __name__ == "__main__":
    sys.exit(run())
