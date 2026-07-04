# CLAUDE.md — `Lotus`

> Agent contract for Claude Code. Read in full before writing code. It governs
> **research methodology first, stack second**. When an instruction here conflicts
> with a convenient shortcut, the instruction wins. Technical artifacts in English;
> discussion with the author in Brazilian Portuguese (§16).

---

## 1. What Lotus is (and is not)

**Lotus** is the core platform of a **quantitative investment fund**. Its two functions are:

1. **Data ingestion** — acquiring and persisting market data (live and historical)
   with integrity and provenance.
2. **Backtesting** — evaluating systematic strategy hypotheses against that data under
   a disciplined, falsification-first methodology, on the **`nautilus_trader`** engine.

Lotus is **not** a live-execution / order-routing system, and it is **not** a place for
ad-hoc exploratory plotting dressed up as research. Backtesting here is a rigorous,
pre-registered process (§7), not a loop of "try parameters until the curve looks good."

A visualization layer (`frontend/`) may sit on top for inspecting data and backtest
results, but it is a **secondary, optional component** (§12). The center of gravity is
the ingestion pipeline and the backtesting engine.

> **Lineage note.** This repository grew out of the `master-of-odds` markets-cockpit
> code (IBKR candle ingestion + a GEX/wall viz skeleton). That code has been rebranded
> and re-homed under the Lotus scope: the ingestion + provenance discipline is kept, the
> GEX/positioning compute is demoted to the optional viz side (`compute/`, §12), and the
> backtesting half — previously absent — is built on `nautilus_trader`.

---

## 2. Architecture & data flow

```
  Historical sources              Live source
  (OptionsDX, ThetaData —         (IBKR)
   vendor stubs, §8)                 │
        │                            ├── ib_async  ──► live bars/snapshots ──► PostgreSQL
        │                            │                                          (system of record)
        │                            └── nautilus IB adapter (ibapi) ──► request historical bars
        │                                                                         │
        └───────────────────────────────────────────────┐                        ▼
                                                          ▼            ParquetDataCatalog
                                          Ingestion layer (Python)     (backtest data source)
                                                          │  provenance + vintage        │
                                                          ▼                              ▼
                                                     PostgreSQL ◄─ ETL ──►  nautilus_trader
                                                          │  (materialize)   BacktestEngine
                                            ┌─────────────┤                       │
                                            ▼             ▼                        ▼
                                     FastAPI (serve   backtest_run /        results → Postgres
                                     data + results)  backtest_result       (run + result rows)
                                            │  HTTP/WS (localhost)
                                            ▼
                                   (optional) TS/Lightweight-Charts viz
```

Two distinct IBKR client stacks coexist and must not be conflated:

- **`ib_async`** (`ingestion/ibkr/`) — the **live** path that writes bars/snapshots into
  Postgres with provenance/vintage. This is the system-of-record ingestion.
- **nautilus's own IB adapter** (`HistoricInteractiveBrokersClient`, built on `ibapi`,
  used in `backtest/download_ib.py`) — pulls **historical** bars into the
  **ParquetDataCatalog**, which is the only data source the backtest engine reads.

**Crypto sources** (public REST, no auth, plain `httpx` — no heavy SDKs):

- **Binance SPOT** (`ingestion/binance/`) — klines backfill + idempotent gap-fill into
  Postgres (`sec_type=CRYPTO`, `source=BINANCE`).
- **Hyperliquid PERP** (`ingestion/hyperliquid/`) — candles + **funding-rate history**
  into Postgres (`sec_type=PERP`, `source=HYPERLIQUID`).
- **`backtest/materialize.py`** is the Postgres→catalog ETL for these sources: it maps
  rows to nautilus `CurrencyPair`/`CryptoPerpetual` instruments (pessimistic taker fees
  on the instrument, consumed by `MakerTakerFeeModel`) and stamps bars at **close time**
  (`ohlc_bar.ts` is open time — close-stamping is what keeps the engine lookahead-free,
  §6.1). All ingestion flows through the shared `ingestion/persistence.py` helpers, so
  the §6.3 invariants (vintage, insert-only idempotency, fail-loud) are written once.

**PostgreSQL is the system of record.** The **ParquetDataCatalog** is nautilus's local
Parquet store and the backtest engine's data source; it is materialized from IBKR/Postgres
and is **gitignored** (`data/`), never the source of truth. Keep concerns separated even
within one repo: **ingestion**, **backtesting compute**, **API/serving**, and the
**optional front-end** are independent layers. The engine reads the catalog; it does not
call broker/vendor APIs at run time.

---

## 3. Tech stack (authoritative)

- **Python** `>=3.12,<3.15`, **pinned to 3.13** (`.python-version`) to guarantee
  prebuilt `nautilus_trader` wheels on macOS ARM. Fully type-hinted.
- **Backtest engine: `nautilus_trader`** (≥ 1.230), installed with the IB extra
  (`nautilus_trader[ib]`). Rust/Cython core, prebuilt wheels — no toolchain needed. This
  is a deliberate choice over a purpose-built vectorized engine: nautilus gives a
  deterministic, timestamp-ordered event engine whose backtest and live code paths are
  identical, which structurally prevents lookahead **within the engine** (§6.1). What it
  does **not** give us for free — survivorship, restatements, correct `ts_event` on loaded
  data, cost realism — remains **our** responsibility (§6, §7). Verify any nautilus API
  against the installed version before use (§14); its surface moves between releases.
- **`ib_async`** (asyncio-native successor to `ib_insync`) for IBKR **live** ingestion.
  Do not block the event loop.
- Historical data via **vendor clients** (OptionsDX EOD chains, ThetaData, …) — currently
  **package stubs** (`ingestion/vendors/`); confirm each vendor's real history window and
  field coverage before depending on it.
- **FastAPI** + **Pydantic v2** + **Uvicorn** for the API (serving data and backtest
  results). **PostgreSQL** ≥ 15 as the system of record; **TimescaleDB** is a proposed,
  not imposed, optional extension for the time-series tables.
- **SQLAlchemy 2.0 (async)** + **asyncpg** + **Alembic** migrations.
- Visualization (optional, §12): vanilla TypeScript + **TradingView Lightweight Charts v5**
  + **Vite** (`frontend/`).

---

## 4. Repository layout (actual)

Top-level importable packages (no umbrella `backend/` package — §5 runs modules directly):

```
lotus/
├── CLAUDE.md
├── core/                 # cross-cutting: config.py (settings, dealer-sign), provenance.py
├── ingestion/
│   ├── persistence.py    # shared §6.3 layer: NormalizedBar/FundingRate, insert-only stores
│   ├── ibkr/             # ib_async live client + bars.py + `python -m ingestion.ibkr`
│   ├── binance/          # Binance SPOT klines (public REST) + `python -m ingestion.binance`
│   ├── hyperliquid/      # Hyperliquid PERP candles + funding + `python -m ingestion.hyperliquid`
│   ├── vendors/          # OptionsDX / ThetaData — STUBS (§8)
│   └── quality/          # gap detection, immutability, point-in-time — STUBS (§6.3)
├── backtest/
│   ├── catalog/          # ParquetDataCatalog access helpers
│   ├── engine/           # nautilus BacktestEngine wiring (venue/account by instrument class)
│   ├── costs/            # pessimistic cost model (§6.4)
│   ├── strategies/       # one module per strategy (sma_cross = plumbing validation)
│   ├── hypotheses/       # pre-registration registry + failure cemetery + stress windows
│   ├── download_ib.py    # historical MES/futures download → catalog (nautilus IB adapter)
│   ├── materialize.py    # Postgres→catalog ETL for crypto (close-time stamping, §6.1)
│   └── run.py            # run a backtest, print tail metrics, persist provenance
├── api/                  # FastAPI routers (bars, instruments, research) + Pydantic schemas
├── db/                   # SQLAlchemy models + Alembic migrations (§9)
├── compute/              # GEX/walls — optional viz support, STUB (§12)
├── frontend/             # OPTIONAL Lightweight Charts viz (§12)
├── tests/
├── docker-compose.yml    # postgres:16 (POSTGRES_PORT overridable; timescale optional)
└── .env.example          # never commit a real .env; the IB Gateway .dmg is gitignored
```

---

## 5. Development commands

- Deps: `uv sync --extra dev` (creates `.venv`; Python pinned via `.python-version`).
- Environment: `cp .env.example .env` and edit.
- DB up: `docker compose up -d postgres`. If host port 5432 is taken (e.g. an SSH tunnel),
  publish elsewhere: `POSTGRES_PORT=55432 docker compose up -d postgres` and set
  `DATABASE_URL=...@127.0.0.1:55432/lotus`.
- Migrate: `uv run alembic upgrade head`.
- Live ingest (needs a reachable Gateway/TWS): `uv run python -m ingestion.ibkr ingest SPY`.
- Download futures history → catalog: `uv run python -m backtest.download_ib --symbol MES
  --expiry 202609 --start 2026-06-22 --end 2026-07-02 --bar-spec 1-HOUR-LAST --no-rth`.
- Crypto backfill (idempotent re-runs fill gaps):
  `uv run python -m ingestion.binance ingest BTCUSDT --interval 1h --start 2026-05-01`;
  `uv run python -m ingestion.hyperliquid ingest-bars BTC --interval 1h --start 2026-05-01`;
  `uv run python -m ingestion.hyperliquid ingest-funding BTC --start 2026-06-01`.
- Materialize crypto → catalog: `uv run python -m backtest.materialize --symbol BTCUSDT
  --source BINANCE --timeframe 1h` (idem `--symbol BTC --source HYPERLIQUID`).
- Run a backtest: `uv run python -m backtest.run --symbol MES --bar-spec 1-HOUR-LAST`
  (crypto: `--symbol BTCUSDT --bar-spec 1-HOUR-LAST --size 0.01`).
- API: `uv run uvicorn api.main:app --host 127.0.0.1 --port 8000`.
- Tests: `uv run pytest`; Lint/format: `uv run ruff check` / `uv run ruff format`.

Do not invent commands that aren't wired up.

---

## 6. Domain invariants — NON-NEGOTIABLE

### 6.1 No lookahead, ever — point-in-time correctness
A backtest may only use information available as of the simulated decision time: no future
data, no restated values, no survivorship-filtered universes. Data carries a **vintage**;
backtests query **as-of**. nautilus enforces strict timestamp ordering within the engine,
but that guarantee is only as good as the `ts_event` on the bars we load — loading correct,
un-restated, vintage-tagged data is on us.

### 6.2 Assumptions are not observables
Where Lotus derives a quantity that depends on an unobserved convention, that dependence
must be **explicit and configurable**. The load-bearing example: **dealer-sign in any
GEX/positioning signal** (`DEALER_SIGN_CONVENTION`). Such values carry an
**`assumption_dependent`** marker end-to-end (config → `gex_result` → `GexSnapshotOut` →
`/api/meta`), and no copy anywhere asserts dealer intent as known fact.

### 6.3 Provenance and integrity
Every stored datum records its **source, capture timestamp, and vintage** (`vintage` is
non-null on `ohlc_bar` and `option_chain_snapshot`). Ingestion **fails loudly** on gaps,
empty results, or partial chains rather than interpolating or forward-filling silently —
record the hole, never fabricate a bar. A `backtest_run` records the exact **data window,
cost model, and code version (git SHA)**, with a unique `config_hash`, so results are
reproducible and identical runs are not double-counted.

### 6.4 Costs are first-class, defaults pessimistic
Model commissions, fees, slippage, and spread explicitly; when uncertain, default to the
**pessimistic** estimate. The MES cost model (`backtest/costs/`) charges **$1.00/contract**
(worse than the ~$0.87 realistic all-in) and assumes orders **always slip one tick**
against us. Options fills (wide OTM spreads) are where edge dies — never assume mid.

### 6.5 Honest defaults and self-correction
When a parameter/convention is uncertain, choose the conservative/explicitly-flagged option
and surface the uncertainty. When infrastructure is missing (e.g. Postgres down), degrade
loudly and say so — `backtest/run.py` prints `NOT PERSISTED …` rather than pretending. Flag
uncertainty over projecting false confidence; self-correct when you've overstated something.

---

## 7. Backtesting methodology — the pre-registration discipline

Falsification-first. The dominant risks are **overfitting and multiple testing**.

### 7.1 A hypothesis is not valid until pre-registered
Before touching test data, a hypothesis is recorded in the **registry**
(`backtest/hypotheses/register_hypothesis`, table `hypothesis`) with all four of:
a **comparative claim against an unconditional baseline**; a **signal threshold frozen
ex-ante on the dev split**; a **kill test** aimed at the weakest assumption; and explicit
**kill criteria**. `register_hypothesis` refuses if any field is empty.

### 7.2 The failure cemetery
`kill_hypothesis` moves a hypothesis to `status='killed'` — it is **never deleted**. The
cemetery (`/api/cemetery`) is the visible denominator of "how many things did we try."

### 7.3 Replication gate before proprietary work
Before any proprietary hypothesis for a strategy track, the engine must **replicate a known
public benchmark** for that domain (equity-vol track: the **CBOE PUT index**). **This gate
is not yet green** — it needs options history we do not yet ingest. Until it is, no
proprietary hypothesis is tested. The current MES run is an **engine-plumbing validation**
(`run_kind='engine_validation'`, null `hypothesis_id`), explicitly **not** a proprietary
result and not evidence of edge.

### 7.4 Mandatory stress windows
Every strategy is evaluated across crisis periods, not just calm samples. The equity/index
set is wired in `backtest/hypotheses/STRESS_WINDOWS` (Volmageddon 2018, COVID 2020, 2022
rate bear, Aug 2024 spike); each run records per-window coverage. A strategy tested only on
benign data is not tested.

### 7.5 Dev/test hygiene, walk-forward, and the tail
Strict dev/test split; the test split is evaluated **once**, after parameters are frozen;
prefer **walk-forward**. Report **tail metrics** (max drawdown, worst-window loss) — never
averages alone, never a high win rate as evidence for a short-convexity strategy.
`backtest/run.py` prints and stores tail metrics as first-class output.

> A risk premium (e.g. the variance risk premium) is *compensation for bearing risk*, not a
> free anomaly. Timing it is a proprietary hypothesis assuming the past mirrors the future —
> treat it as such, with kill criteria, not as a guarantee embedded in the data.

---

## 8. Data sourcing notes

- **Live (IBKR / `ib_async`)**: bars, and option-chain snapshots with OI + greeks. IBKR
  runs headless via **IB Gateway + IBC**; the session can drop, so ingestion must reconnect
  gracefully and log every state transition. Respect market-data pacing limits.
- **Backtest history (nautilus IB adapter)**: `HistoricInteractiveBrokersClient` →
  `request_instruments` then `request_bars`. **Request bars by resolved `instrument_ids`,
  not by re-passing a raw `IBContract`** (the bare futures contract fails simplified-symbology
  re-parsing). **Contract-lifespan gotcha:** nautilus rejects orders outside a futures
  contract's `activation`/`expiration` window — IB's `activation` for a lead contract is the
  roll date, not first-trade. Backtest **within the contract's active window** (use intraday
  bars there to get enough history) or pick a contract active over the target window. IB does
  **not** provide usable historical option OI, so historical-options backtests need a vendor.
- **Binance SPOT** (public REST, no auth): `GET /api/v3/klines` paginated by advancing
  startTime past the last closeTime (limit 1000/call, weight 2), quote currency read
  from `exchangeInfo`. Rate hygiene: 6000 weight/min/IP via the `X-MBX-USED-WEIGHT-1m`
  header; 429 → Retry-After backoff; **418 = ban, never retry; 451 = geo-block** (US
  and other restricted IPs — this host is in Brazil). The in-progress kline is dropped
  (insert-only store cannot restate). Deep 1m history exists as bulk dumps at
  data.binance.vision (follow-up; 2025+ files use **microsecond** timestamps).
- **Hyperliquid PERP** (public info API, no auth): single `POST /info`.
  **candleSnapshot serves only the most recent ~5000 candles per coin+interval**
  (1d≈13.7y, 1h≈208d, 1m≈3.5d — no paging back); a request older than that **fails
  loud** unless `--allow-truncated` is passed explicitly. `fundingHistory` paginates to
  inception (500 rows/call, hourly accrual) → `funding_rate` table. **No historical
  open-interest API** (flagged gap; S3 asset_ctxs unverified). Accumulating deep 1m perp
  history requires a live WebSocket collector — follow-up, not yet built.
- **Historical vendors**: OptionsDX / ThetaData are **stubs** today. Confirm real coverage
  before depending on any.
- **Environment reality (this host)**: the IB Gateway runs a **live (non-paper) account on
  port 4001**, used for **READ-ONLY historical data only** (§15). All sources flow through the
  same provenance/vintage tagging (§6.3); never mix vendors into one series without recording
  which datum came from where.

---

## 9. Data model (PostgreSQL)

Refine via Alembic; migrations `0001` (seed), `0002` (vintage + research), and `0003`
(crypto precision + funding) are applied.

**Market data**
- `instrument` — symbol, sec_type (`STK`/`FUT`/`CRYPTO`/`PERP`), exchange, currency,
  multiplier, conid. Unique `(symbol, sec_type)` — Binance `BTCUSDT/CRYPTO` and
  Hyperliquid `BTC/PERP` coexist.
- `ohlc_bar` — instrument_id, ts (bar **open** time), timeframe, o/h/l/c
  `Numeric(30,12)` / volume `Numeric(30,10)` (crypto-wide precision, bumped in 0003),
  source, captured_at, **vintage (non-null)**.
- `funding_rate` — instrument_id, ts, rate, premium, source, captured_at, **vintage**;
  unique `(instrument_id, ts)`. Perp funding is a first-class cost input (§6.4).
- `option_chain_snapshot` — instrument_id, captured_at, expiry, source, **vintage**;
  immutable.
- `option_quote` — snapshot_id, strike, right, open_interest, gamma, iv.
- `gex_result` — snapshot_id, dealer_sign_convention, assumption_dependent, profile,
  call_wall, put_wall (optional viz side, §12).

**Research (§7)**
- `hypothesis` — statement, baseline, signal_threshold, dev_split_def, kill_test,
  kill_criteria, status (`registered`/`live`/`killed`), registered_at, killed_at,
  kill_reason. (The §7.1 registry; `killed` rows are the §7.2 cemetery.)
- `backtest_run` — hypothesis_id (nullable for replication/validation runs), strategy,
  params, data_window, cost_model, code_version (git SHA), **config_hash (unique)**,
  created_at.
- `backtest_result` — run_id (unique), headline, **stress_windows**, **tail**,
  equity_curve_ref, computed_at.

Constraints: immutable snapshot/quote rows; `captured_at`/`vintage` never null; uniqueness
to prevent duplicate snapshots and duplicate runs of identical config.

---

## 10. API contract (FastAPI)

- REST: instrument list; historical bars (instrument + timeframe + range, carrying
  `source`/`vintage`); as-of chain snapshots; and **research** endpoints —
  `/api/hypotheses`, `/api/cemetery`, `/api/backtest-runs`,
  `/api/backtest-runs/{id}/result`. All read-only.
- Any GEX/positioning payload **must include** the dealer-sign convention and
  `assumption_dependent: true` (§6.2). `/api/meta` surfaces the convention.
- **Bind to `127.0.0.1`.** No public exposure; remote access is an explicit
  SSH-tunnel/VPN decision by the author, never a code default.

---

## 11. (Removed — front-end is not a core concern; see §12)

## 12. Visualization (OPTIONAL, secondary)

`frontend/` is Vite + TypeScript + **Lightweight Charts v5** (one candle tile today). Its
job is **inspecting** data and results, not driving the system. Call/put walls render as
labeled price lines carrying the assumption marker (§6.2) — not support/resistance facts.
The GEX-by-strike profile needs a custom series/plugin. **TradingView attribution is
required** (`attributionLogo` / visible link) — do not strip it. Do not let viz work block
§13 milestones.

---

## 13. Milestones (gates — thin slice first)

- **M0 — ingestion skeleton** ✅: one instrument's daily bars into Postgres via `ib_async`,
  with provenance/vintage.
- **M1 — data integrity** (in progress): multi-source ingestion, option-chain snapshots
  with OI + greeks, quality checks (gap detection, immutability, point-in-time). Vendor +
  quality packages are stubs.
- **M2 — backtest harness** ✅ (plumbing) / ⛔ (gate): nautilus engine with pessimistic
  costs and point-in-time catalog data runs end-to-end on **real MES bars** and persists a
  reproducible run/result. The **replication gate (§7.3) is still red** — no proprietary
  work until it is green.
- **M3 — pre-registration workflow** (partial): registry + cemetery + stress-window wiring
  exist; dev/test-split enforcement and walk-forward are still to be wired into every run.
- **M4 — optional viz**: Lightweight Charts inspection of data and results.

Do not start proprietary testing while §7.3 is red.

---

## 14. Guardrails — what NOT to do

- Do **not** introduce lookahead, restated data, or survivorship-filtered universes (§6.1).
- Do **not** run backtests without realistic, pessimistic costs (§6.4).
- Do **not** test proprietary hypotheses before the replication gate is green (§7.3), and do
  **not** test any hypothesis not pre-registered with all four §7.1 fields.
- Do **not** delete killed hypotheses — they belong in the cemetery (§7.2).
- Do **not** report averages while hiding tail/drawdown, or treat a high win rate as evidence
  for a short-convexity strategy (§7.5).
- Do **not** present GEX/positioning as observed fact — carry the dealer-sign marker (§6.2).
- Do **not** fabricate, interpolate, or forward-fill missing data silently (§6.3).
- Do **not** put secrets in the repo or bind the API / Postgres to a public interface (§15).
- Do **not** add live order-routing/execution logic — out of scope. Nautilus's live exec
  factories are intentionally **not** wired.
- Do **not** add frameworks/abstractions beyond the current milestone. The author pushes back
  on unwarranted complexity.
- Do **not** invent nautilus/ib_async/vendor API methods — verify against the installed
  version/current docs; if unverifiable, stop and ask.

---

## 15. Security & secrets

- **No credentials in the repo, ever.** IBKR login, IBC config, vendor API keys, and DB
  credentials come from env vars / a gitignored `.env` / a secrets manager. Commit only
  `.env.example`. The IB Gateway installer (`*.dmg`) and the Parquet `data/` catalog are
  gitignored.
- **Live-Gateway read-only decision (bounded).** This host talks to a **live-account** IB
  Gateway on **port 4001**, used **only** to read historical data for the catalog — no order
  routing, no execution factories. This is a deliberate, explicit deviation from a
  paper-first default: anything that could **place an order** must point at a **paper**
  endpoint first. The reduced-2FA trading-platform login makes host compromise high-stakes —
  keep the box hardened (key-only SSH, no inbound beyond what's required).
- Postgres is **not** network-exposed; the API is **localhost-bound**. Never log secrets.

---

## 16. Working style with the author

- Technical artifacts (code, identifiers, this file) in **English**; discussion and rationale
  in **Brazilian Portuguese**.
- Prefer **dense, flowing prose** over bullet soup in design notes and docstrings.
- **Flag uncertainty explicitly** and **self-correct** when you've overstated certainty or
  added unrequested scope — the author treats that as a feature.
- Implementation is the criterion for "done": a claim that something works means it runs and
  is tested, not that it looks plausible. Leitura sem implementação dá a ilusão de domínio;
  o código não deixa mentir.
```
