# CEMETERY — Intraday Regime-Conditioned Momentum (v1)

**Killed:** 2026-07-04
**Registration:** `registration/2026-07-04_intraday_regime_momentum.md`
(sha256 `34d3cfba82d310247a791c4ee1452b11c8e83def7caf7c2071a83fb6775f3cdd`, approved 2026-07-04)
**Gate that fired:** **R1 replication gate (Phase 3)** — committed criterion: expected
positive sign with HAC (Newey-West) t ≥ 2 on the dev split, required jointly for SPY
(canonical prev-close variant) AND BTCUSDT AND ETHUSDT.

## Hypothesis statement (as registered)

A frozen regime classifier at session open+30min (|r1| ≥ 70th pct of trailing 60
sessions, direction = sign(r1)) identifies sessions where open+30→close sign-following
momentum has positive expectation (H1), and conditioning on it improves net
total-capital Sharpe vs unconditional momentum under pessimistic costs (H2). Both
hypotheses required the R1 replication gate to pass first.

## The numbers that killed it (dev split, < 2025-07-01)

| instrument | n | beta | HAC t | required | verdict |
|---|---|---|---|---|---|
| SPY (from prev close, canonical) | 5064 | +0.0442 | **+2.27** | yes | PASS |
| SPY (from open) | 5065 | −0.0663 | −1.43 | no (reported) | fail |
| BTCUSDT | 2870 | −0.0327 | **−1.13** | yes | **FAIL** |
| ETHUSDT | 2870 | −0.0110 | **−0.42** | yes | **FAIL** |
| SOLUSDT | 1784 | +0.0259 | +1.26 | no (reported) | fail |
| BNBUSDT | 2789 | −0.0304 | −0.90 | no (reported) | fail |
| ADAUSDT | 2630 | +0.0247 | +1.25 | no (reported) | fail |

Full tables incl. per-year stability: `reports/r1_replication.md`.

## What was learned (recorded so the denominator stays visible, §7.2)

1. **Crypto intraday momentum (UTC-session construction) did not replicate**: BTC and
   ETH betas are small and NEGATIVE (reversal-leaning), nowhere near significance. The
   entire crypto leg of the idea rests on a phenomenon we could not reproduce on ~8
   years of 5-minute data with HAC inference.
2. **SPY canonical replication passed on the full dev sample but is front-loaded**:
   per-year betas are strongly positive 2005–2013 (t up to 3.76 in 2013) and mostly
   flat-to-negative 2015+ (2021: t = −2.35). Consistent with post-publication decay of
   the Gao et al. (2018) effect, whose sample ended 2013.
3. Phases 4–6 (H1 classifier, H2 Nautilus backtest) were never evaluated — the
   registration's gate ordering killed the idea before any strategy P&L was computed,
   which is the point of the protocol: no opportunity to admire a curve built on a
   mechanism that does not exist.

## Disposition

- H1 (Postgres hypothesis id=1): killed, reason "R1 gate failed: BTC t=-1.13, ETH t=-0.42 (dev)".
- H2 (Postgres hypothesis id=2): killed, same reason (gate precedes H2 by construction).
- Any revival (e.g., US-only variant exploiting the SPY prev-close pass; different
  session construction for crypto) is a **NEW registration** with fresh kill criteria —
  it counts against the multiple-testing denominator, and the per-year decay table
  above must be confronted in its design.
