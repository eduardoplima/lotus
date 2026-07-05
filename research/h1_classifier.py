"""Phase 4 — H1 classifier skill (dev split only; vectorized pandas).

Conditional (frozen flag) vs baselines:
  (a) unconditional — trade every session on sign(r1);
  (b) US leg only — gap-only variant (same rule computed on the overnight gap).

Metrics per instrument and aggregated: mean net bps/trade, HAC t, hit rate,
exposure (% flagged), and TOTAL-CAPITAL Sharpe with abstentions at zero — the
decision criterion (per-trade metrics mechanically improve under selection and
are explicitly NOT the criterion).

Costs per registration §5 (round-trip on notional):
  crypto 2×(10bps taker + 5bps slip) = 30 bps; SPY research haircut 2×1bp = 2bps
  (gross also reported); MES $0.623×2 + $1.25×2 per contract on price×5 notional.
Sensitivity: 2× slippage (crypto 40bps RT; SPY 4bps RT; MES $0.623×2+$2.50×2).

Proceed to Phase 5 only if the conditional total-capital uplift is positive on dev.
"""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from research.sessions import add_signal, crypto_session_table, us_session_table
from research.stats import annualized_sharpe, hac_mean_t

CURATED = Path("data/curated")
REPORTS = Path("reports")
DEV_END = pd.Timestamp("2025-07-01")
CRYPTO = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"]

RT_COST = {"crypto": 0.0030, "crypto_2x": 0.0040, "spy": 0.0002, "spy_2x": 0.0004}
PPY = {"us": 252.0, "crypto": 365.0}


def _strategy_returns(table: pd.DataFrame, rt_cost: float, conditional: bool) -> pd.Series:
    active = table["flag"] if conditional else (table["direction"] != 0)
    active = active & table["entry_open"].notna() & table["session_close"].notna()
    gross = table["direction"] * table["trade_ret_gross"]
    net = (gross - rt_cost).where(active, 0.0)
    return net.astype(float)


def _mes_returns(table: pd.DataFrame, conditional: bool, slip_mult: float = 1.0) -> pd.Series:
    """MES: per-contract dollar costs on price×5 notional (registration §5)."""
    active = table["flag"] if conditional else (table["direction"] != 0)
    active = active & table["entry_open"].notna() & table["session_close"].notna()
    gross = table["direction"] * table["trade_ret_gross"]
    rt_dollars = 2 * 0.623 + 2 * 1.25 * slip_mult
    cost_frac = rt_dollars / (table["entry_open"] * 5.0)
    return (gross - cost_frac).where(active, 0.0).astype(float)


def _row(name: str, net: pd.Series, table: pd.DataFrame, ppy: float, conditional: bool) -> dict:
    active = (table["flag"] if conditional else (table["direction"] != 0)) & table[
        "entry_open"
    ].notna()
    trades = net[active]
    mu, t, n = (
        hac_mean_t(trades.to_numpy()) if len(trades) > 30 else (float("nan"),) * 2 + (len(trades),)
    )
    return {
        "variant": name,
        "sessions": len(net),
        "trades": int(active.sum()),
        "exposure": float(active.mean()),
        "net_bps_per_trade": mu * 1e4 if trades.size else float("nan"),
        "hac_t_per_trade": t,
        "hit_rate": float((trades > 0).mean()) if trades.size else float("nan"),
        "tc_sharpe": annualized_sharpe(net.to_numpy(), ppy),
    }


def evaluate(sym: str, table: pd.DataFrame, leg: str) -> list[dict]:
    dev = table[table.index < DEV_END]
    rows = []
    if leg == "crypto":
        for cost_label, rt in (("1x", RT_COST["crypto"]), ("2x slip", RT_COST["crypto_2x"])):
            cond = _strategy_returns(dev, rt, conditional=True)
            unc = _strategy_returns(dev, rt, conditional=False)
            r_c = _row(f"conditional [{cost_label}]", cond, dev, PPY["crypto"], True)
            r_u = _row(f"unconditional [{cost_label}]", unc, dev, PPY["crypto"], False)
            r_c["uplift_sharpe"] = r_c["tc_sharpe"] - r_u["tc_sharpe"]
            rows += [r_c, r_u]
    elif leg == "spy":
        for cost_label, rt in (("1x", RT_COST["spy"]), ("2x slip", RT_COST["spy_2x"])):
            cond = _strategy_returns(dev, rt, conditional=True)
            unc = _strategy_returns(dev, rt, conditional=False)
            r_c = _row(f"conditional [{cost_label}]", cond, dev, PPY["us"], True)
            r_u = _row(f"unconditional [{cost_label}]", unc, dev, PPY["us"], False)
            r_c["uplift_sharpe"] = r_c["tc_sharpe"] - r_u["tc_sharpe"]
            rows += [r_c, r_u]
        # gap-only baseline (US only): same frozen rule computed on the gap.
        gap_table = add_signal(
            dev.drop(columns=["signal_threshold", "flag", "direction"]), r1_col="gap"
        )
        gap_table["direction"] = np.sign(gap_table["gap"]).astype(int)
        gap = _strategy_returns(gap_table, RT_COST["spy"], conditional=True)
        rows.append(_row("gap-only conditional [1x]", gap, gap_table, PPY["us"], True))
    else:  # mes
        for slip, cost_label in ((1.0, "1x"), (2.0, "2x slip")):
            cond = _mes_returns(dev, True, slip)
            unc = _mes_returns(dev, False, slip)
            r_c = _row(f"conditional [{cost_label}]", cond, dev, PPY["us"], True)
            r_u = _row(f"unconditional [{cost_label}]", unc, dev, PPY["us"], False)
            r_c["uplift_sharpe"] = r_c["tc_sharpe"] - r_u["tc_sharpe"]
            rows += [r_c, r_u]
    for r in rows:
        r["instrument"] = sym
    return rows


def run() -> int:
    all_rows: list[dict] = []
    crypto_nets_1x: dict[str, pd.Series] = {}

    spy = add_signal(us_session_table(pd.read_parquet(CURATED / "ibkr/SPY_5m.parquet")))
    all_rows += evaluate("SPY", spy, "spy")
    mes = add_signal(us_session_table(pd.read_parquet(CURATED / "ibkr/MES_STITCHED_5m.parquet")))
    all_rows += evaluate("MES", mes, "mes")

    for sym in CRYPTO:
        t = add_signal(crypto_session_table(pd.read_parquet(CURATED / f"binance/{sym}_5m.parquet")))
        all_rows += evaluate(sym, t, "crypto")
        dev = t[t.index < DEV_END]
        crypto_nets_1x[sym] = _strategy_returns(dev, RT_COST["crypto"], conditional=True)

    # Equal-weight crypto aggregate (1x), abstentions at zero.
    agg = pd.DataFrame(crypto_nets_1x).fillna(0.0).mean(axis=1)
    agg_uncond = (
        pd.DataFrame(
            {
                sym: _strategy_returns(
                    add_signal(
                        crypto_session_table(pd.read_parquet(CURATED / f"binance/{sym}_5m.parquet"))
                    ).loc[lambda d: d.index < DEV_END],
                    RT_COST["crypto"],
                    conditional=False,
                )
                for sym in CRYPTO
            }
        )
        .fillna(0.0)
        .mean(axis=1)
    )
    agg_sharpe = annualized_sharpe(agg.to_numpy(), PPY["crypto"])
    agg_uncond_sharpe = annualized_sharpe(agg_uncond.to_numpy(), PPY["crypto"])

    df = pd.DataFrame(all_rows)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    stamp = dt.datetime.now(tz=dt.UTC).isoformat()

    lines = [
        "# H1 — Classifier skill (dev split)",
        "",
        f"Generated {stamp} · code {sha[:12]} · registration sha256"
        f" 34d3cfba… · dev < {DEV_END.date()}",
        "",
        "**Decision criterion is the TOTAL-CAPITAL comparison** (abstentions at zero).",
        "Per-trade metrics mechanically improve under selection and are reported for",
        "context only. Crypto symbols are cross-correlated: the pooled sample is",
        "smaller than the row count suggests; per-symbol rows are shown, no pooled t.",
        "",
        "| instrument | variant | sessions | trades | exposure "
        "| net bps/trade | HAC t | hit | TC Sharpe | uplift |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for _, r in df.iterrows():
        uplift = f"{r['uplift_sharpe']:+.2f}" if pd.notna(r.get("uplift_sharpe")) else ""
        lines.append(
            f"| {r['instrument']} | {r['variant']} | {r['sessions']} | {r['trades']} "
            f"| {r['exposure']:.1%} | {r['net_bps_per_trade']:.1f} | {r['hac_t_per_trade']:.2f} "
            f"| {r['hit_rate']:.3f} | {r['tc_sharpe']:.2f} | {uplift} |"
        )
    lines += [
        "",
        "## Equal-weight crypto aggregate (1x costs, abstentions at zero)",
        "",
        f"- conditional TC Sharpe: **{agg_sharpe:.2f}**",
        f"- unconditional TC Sharpe: **{agg_uncond_sharpe:.2f}**",
        f"- uplift: **{agg_sharpe - agg_uncond_sharpe:+.2f}**",
    ]

    cond_1x = df[df["variant"] == "conditional [1x]"]
    uplift_positive = (
        bool((cond_1x["uplift_sharpe"] > 0).mean() >= 0.5) and (agg_sharpe - agg_uncond_sharpe) > 0
    )
    lines += [
        "",
        "## Phase-4 verdict (mechanical)",
        "",
        "Rule: proceed to Phase 5 only if the conditional total-capital uplift is",
        "positive on dev (crypto aggregate AND at least half of instruments).",
        "",
        "**H1: "
        + ("PROCEED to Phase 5" if uplift_positive else "STOP — uplift not positive on dev")
        + "**",
    ]
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "h1_classifier.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[-3:]))
    print(f"report: {REPORTS / 'h1_classifier.md'}")
    return 0 if uplift_positive else 1


if __name__ == "__main__":
    sys.exit(run())
