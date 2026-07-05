# Pre-Registration — Intraday Regime-Conditioned Momentum (v1)

**Date:** 2026-07-04
**Status:** DRAFT — awaiting human approval. Immutable after approval; any change
thereafter is a new registration.
**Code version at registration:** git 04447ac (+ sprint scaffolding, uncommitted)
**Postgres registry:** H1/H2 rows in the `hypothesis` table carry this file's SHA-256.

---

## 1. Hypotheses and baselines

- **R1a (replication, US).** First-half-hour return predicts last-half-hour return on
  SPY, in the spirit of Gao/Han/Li/Zhou (2018, JFE). Per the human's recollection the
  paper measures the first-half-hour return **from the previous close** (includes the
  overnight gap) — **to be confirmed by the human against the paper**. Both variants
  are implemented and reported: (i) from previous RTH close [canonical pending
  confirmation]; (ii) from same-day open.
- **R1b (replication, crypto).** Same construction per symbol under the UTC session
  convention, in the spirit of Shen/Urquhart/Wang (2022). **The paper's exact session
  convention must be confirmed by the human; it is not guessed here.** In a 24/7 market
  previous close = session open, so a single variant exists.
- **H1 (informational).** The frozen classifier's "trade" flag identifies sessions where
  sign-following momentum from open+X to session close has positive expectation, with
  uplift over (a) unconditional momentum every session and, US leg only, (b) a gap-only
  variant of the same rule.
- **H2 (economic).** Conditioning improves **net total-capital Sharpe** vs unconditional
  momentum in a NautilusTrader backtest under the pessimistic cost table (§5).

## 2. Frozen parameters (v1 — arbitrary-but-frozen; no tuning)

- **X = 30 minutes.**
- **US session:** RTH 09:30–16:00 America/New_York, DST-aware.
  Gap = open(t) / previous RTH close(t−1) − 1.
- **Crypto session:** 00:00–24:00 UTC; session open = 00:00 UTC. No separate gap
  feature: in a 24/7 market there is no overnight halt, so the first-X return already
  absorbs any discontinuity a gap feature would capture.
- **Signal rule (identical both legs):** r1 = return from session open to open+X.
  Trade flag iff |r1| ≥ 70th percentile of |r1| over the trailing 60 sessions
  (crypto sessions = calendar days), computed EXCLUDING the current session.
  Direction = sign(r1). Otherwise abstain.
- **Trade mechanics:** enter at the first bar open strictly after open+X; exit at
  session close (US 16:00 NY; crypto 00:00 UTC next day). One decision per instrument
  per session. Always flat overnight.
- **Sizing:** 1 MES contract; fixed 1,000 USDT notional per crypto symbol; equal fixed
  notional per instrument for aggregation. Total-capital Sharpe on full allocated
  notional; abstention sessions count at zero return.

## 3. Universe (frozen at approval)

Selection rule as executed (interpretation on record): USDT spot pairs listed ≥ 4 years
before registration date (i.e., before 2022-07-04) **and still listed at registration
date**, ranked by total quote (USDT) volume in the anchor month **2022-07** (the month
the ≥4y eligibility anchors to); top 3 beyond BTCUSDT/ETHUSDT.

Executed ranking (July-2022 quote volume, from data.binance.vision daily archives):
SOL 5.49B > BNB 4.37B > MATIC 4.36B > ADA 3.13B > XRP 2.96B > AVAX 2.53B > ...

- **MATICUSDT is excluded**: the pair no longer exists in 2026 (MATIC→POL migration;
  no archives past 2024). **Survivorship caveat, on record:** requiring "still listed"
  biases the crypto universe toward survivors. Accepted for this sprint because no
  cross-sectional crypto claim is being made; the bias is stated, not hidden.
- **Frozen universe:** SPY (research), MES (execution), **BTCUSDT, ETHUSDT, SOLUSDT,
  BNBUSDT, ADAUSDT**.

## 4. Sample periods (from preflight probes, 2026-07-04)

| Instrument | Earliest available | Source of truth |
|---|---|---|
| SPY 5m TRADES | 1993-01-29 (IB head timestamp) | IBKR Gateway (read-only, port from env) |
| MES continuous 5m | 2023-06-18 (IB head timestamp, ContFuture) | IBKR Gateway |
| BTCUSDT 5m | 2017-08 | data.binance.vision monthly archives |
| ETHUSDT 5m | 2017-08 | idem |
| BNBUSDT 5m | 2017-11 | idem |
| ADAUSDT 5m | 2018-04 | idem |
| SOLUSDT 5m | 2020-08 | idem |

- SPY download window: 2005-01-01 → present (21+ years is ample power; earlier data adds
  microstructure-regime noise; frozen choice, stated not tuned).
- **Splits:** holdout = final 12 months (2025-07-01 → 2026-06-30), touched exactly once
  after all dev decisions are closed; dev = everything before 2025-07-01.
- MES leg is short (≈2y dev) — it serves cost realism, not statistical power (SPY does).

## 5. Cost table (pessimistic, per side; verified 2026-07-04)

| Leg | Commission | Slippage | Verification |
|---|---|---|---|
| MES | **USD 0.623 all-in** (IBKR fixed 0.25 + CME exchange 0.353 + NFA 0.02) | 1 tick = 0.25 pts = **USD 1.25** | interactivebrokers.com commissions-futures.php + accounts/fees/CME.php (live pages, 403 to plain fetch — read via rendered page) |
| Crypto spot | **taker 10 bps** (VIP 0, no BNB discount) | **5 bps** | binance.com/en/fee/trading |
| SPY (research proxy, not traded here) | gross AND 1 bp/side haircut, both reported | — | stated as proxy |

- **Sensitivity:** all headline tables re-run at **2× slippage**.
- Gross numbers never appear without net alongside.

## 6. Kill criteria (numeric, committed now)

- **R1 gate:** replication effect has the expected sign with HAC (Newey-West) t ≥ 2 on
  the dev split — required for SPY (R1a) and for at least BTCUSDT AND ETHUSDT (R1b).
  Otherwise: cemetery entry, sprint ends.
- **H2 kill:** on dev, kill unless ALL of:
  net total-capital Sharpe (conditional) ≥ **0.5**, AND uplift over unconditional ≥
  **+0.2 Sharpe**, AND uplift sign consistent in ≥ **60%** of calendar years AND in at
  least **half** of the crypto symbols. *(Thresholds are proposals — confirm or amend
  at this approval.)*
- Holdout: evaluated once, only if dev survives, only to confirm or kill.

## 7. Hypothesis budget

This registration covers **R1a, R1b, H1, H2 — nothing else**. Any new feature, session
boundary, threshold, symbol, or holding rule is a new registration.

## 8. Environment (logged)

Python 3.13.5 · nautilus_trader 1.230.0 · ib_async 2.1.0 · pandas 3.0.3 · numpy 2.5.0 ·
scipy 1.18.0 · matplotlib 3.11.0 · pyarrow 24.0.0 · uv-locked (`uv.lock`).
IB Gateway: live account, **read-only**, host/port/clientId from env (4001 at preflight).
Preflight artifacts: SPY 78×5m RTH bars + MES 228×5m bars retrieved 2026-07-04;
BTCUSDT-5m-2026-05 archive checksum-verified (timestamps in **microseconds** — 2025+
archives; earlier are milliseconds; normalized on parse).

## 9. Known deviations & flags (on record at registration)

1. Research data lives in `data/raw` (immutable archives) + `data/curated` (UTC Parquet)
   per the sprint spec — a documented deviation from Lotus's Postgres system-of-record
   for this sprint's research artifacts.
2. Universe-rule interpretation ("first month of the sample" → anchor month 2022-07) was
   chosen by the agent and is subject to human amendment at THIS approval only.
3. R1a canonical variant (from previous close) pends human confirmation against the
   Gao et al. paper; R1b session convention pends confirmation against Shen et al.
4. Published effect magnitudes for the comparison columns: **not provided** — the human
   may supply the papers; numbers will not be fabricated.
5. MES continuous history only reaches 2023-06 on this account — MES is execution
   realism, not power (SPY carries R1a/H1 power).

---

**APPROVAL LINE — the human approves or amends everything above; upon approval this
file is immutable and Phase 2 (bulk data) may begin.**
