# Data QA — Phase 2 (curated immutable after this sign-off)

Generated 2026-07-04T18:21:39.398459+00:00 · code 04447aced03a · registration sha256 34d3cfba…

| instrument | rows | first | last | sessions | missing | dup ts | zero-vol |
|---|---|---|---|---|---|---|---|
| BTCUSDT | 931369 | 2017-08-17 04:00 | 2026-06-30 23:55 | 3235 | 4.0 | 0 | 932 |
| ETHUSDT | 931369 | 2017-08-17 04:00 | 2026-06-30 23:55 | 3235 | 4.0 | 0 | 1817 |
| SOLUSDT | 618845 | 2020-08-11 06:00 | 2026-06-30 23:55 | 2149 | 0.0 | 0 | 191 |
| BNBUSDT | 908127 | 2017-11-06 03:50 | 2026-06-30 23:55 | 3154 | 4.0 | 0 | 2164 |
| ADAUSDT | 861916 | 2018-04-17 04:00 | 2026-06-30 23:55 | 2995 | 1.0 | 0 | 181 |
| SPY | 419387 | 2005-01-03 14:30 | 2026-06-30 19:55 | 5310 | nan | 0 | 111 |
| MES_STITCHED | 149950 | 2024-05-01 22:00 | 2026-07-03 16:55 | 522 | nan | 0 | 2078 |

- **DST spring-forward integrity (SPY):** OK — 09:30 NY bar present after every spring-forward
- **SPY ex-div dates flagged:** 80 dates (TRADES vs ADJUSTED_LAST close-ratio steps),
  saved at `data/curated/ibkr/spy_exdiv_dates.csv`. Overnight gaps across these dates are
  mechanically distorted; the research series stays UNADJUSTED per registration — the
  gap feature is affected only via the r1-from-prev-close variant on ~quarterly dates.
- 'missing' for US = business days minus sessions (US market holidays are expected, ~9-10/yr).
- Zero-volume crypto bars are early-listing illiquidity; kept as-is (no fabrication).

**QA sign-off: curated data frozen for Phases 3-5.**
