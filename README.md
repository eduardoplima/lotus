# Lotus

**Lotus** is the core platform of a quantitative investment fund. Two functions:

1. **Data ingestion** — market data (live via IBKR/`ib_async`, historical via the
   `nautilus_trader` IB adapter, **Binance spot** and **Hyperliquid perp** public REST,
   and, later, options vendors) persisted to **PostgreSQL** with provenance and vintage.
2. **Backtesting** — systematic strategy hypotheses evaluated on the
   **[`nautilus_trader`](https://github.com/nautechsystems/nautilus_trader)** engine
   under a falsification-first, pre-registered methodology (no lookahead, pessimistic
   costs, mandatory stress windows, a failure cemetery).

A TypeScript + TradingView Lightweight Charts front-end (`frontend/`) is an **optional**
inspection layer, not a core function. See [`CLAUDE.md`](./CLAUDE.md) for the full scope
and the non-negotiable domain invariants.

> Every GEX/wall number rests on an **assumed** dealer-sign convention
> (`DEALER_SIGN_CONVENTION`) — a modeled assumption, not a measured fact — and every such
> value is marked `assumption_dependent`. Do not read the chart as ground truth.

## Status

- **M0 (ingestion skeleton)** ✅ — daily bars → Postgres via `ib_async`, with provenance/vintage.
- **Crypto ingestion** ✅ — Binance SPOT klines and Hyperliquid PERP candles + full
  funding-rate history, backfilled via public REST (no auth) with idempotent re-runs,
  through the shared `ingestion/persistence.py` layer.
- **M2 (backtest harness)** ✅ *plumbing* — the nautilus engine runs end-to-end on **real
  MES bars** pulled from IB Gateway AND on **real BTC spot/perp bars** (materialized
  Postgres→catalog), under pessimistic cost models, persisting reproducible
  `backtest_run` + `backtest_result` rows. The **replication gate (§7.3) is still
  red**, so these runs are *engine validations*, **not** proprietary results.

## Requirements

- Python 3.13 (pinned via `.python-version`; project supports `>=3.12,<3.15`)
- [`uv`](https://docs.astral.sh/uv/), Docker + Docker Compose, Node 20+ (for the viz)
- An IB Gateway/TWS reachable from this host for the ingestion/download steps

## Setup

```bash
uv sync --extra dev            # backend deps incl. nautilus_trader[ib]
cp .env.example .env           # edit as needed; .env is gitignored

# Postgres. If host port 5432 is free:
docker compose up -d postgres
# If 5432 is taken (e.g. an SSH tunnel), publish elsewhere and match DATABASE_URL:
POSTGRES_PORT=55432 docker compose up -d postgres
export DATABASE_URL="postgresql+asyncpg://lotus:lotus@127.0.0.1:55432/lotus"

uv run alembic upgrade head    # creates the §9 schema (market data + research tables)
```

## The MES backtest, end-to-end

The IB Gateway must be running and logged in. On this host it runs a **live account on
port 4001**, used **read-only** for historical data (see `.env.example`, §15 of CLAUDE.md).

```bash
# 1. Download Micro E-mini S&P 500 (MES) hourly bars, within the contract's active window,
#    into the nautilus ParquetDataCatalog (gitignored under data/).
uv run python -m backtest.download_ib \
  --symbol MES --expiry 202609 \
  --start 2026-06-22 --end 2026-07-02 \
  --bar-spec 1-HOUR-LAST --no-rth

# 2. Run the SMA-cross plumbing backtest (pessimistic costs, tail metrics, provenance).
uv run python -m backtest.run --symbol MES --bar-spec 1-HOUR-LAST --fast 10 --slow 30
```

`run.py` prints headline **and** tail/drawdown metrics and writes a `backtest_run` (git
SHA, data window, cost model, unique config hash) + `backtest_result` row to Postgres. It
labels the run `engine_validation` with a null `hypothesis_id` — it is not a discovery.

> **Contract-lifespan gotcha:** nautilus rejects orders outside a futures contract's
> `activation`/`expiration` window, and IB reports a lead contract's `activation` as the
> roll date — so a full-history *daily* backtest of a fresh front month gets rejected.
> Backtest within the active window (intraday bars give enough history), or pick a contract
> active over your target window.

## Crypto ingestion + backtest, end-to-end

Public REST, no API keys. Binance geo-blocks restricted IPs with HTTP 451 (US etc.) —
this host (Brazil) is fine.

```bash
# 1. Backfill into Postgres (idempotent — re-runs fill gaps, restate nothing)
uv run python -m ingestion.binance ingest BTCUSDT --interval 1h --start 2026-05-01
uv run python -m ingestion.hyperliquid ingest-bars BTC --interval 1h --start 2026-05-01
uv run python -m ingestion.hyperliquid ingest-funding BTC --start 2026-06-01

# 2. Materialize Postgres → nautilus catalog (CurrencyPair / CryptoPerpetual)
uv run python -m backtest.materialize --symbol BTCUSDT --source BINANCE --timeframe 1h
uv run python -m backtest.materialize --symbol BTC --source HYPERLIQUID --timeframe 1h

# 3. Validation backtests (CASH account for spot, MARGIN/USDC for the perp)
uv run python -m backtest.run --symbol BTCUSDT --bar-spec 1-HOUR-LAST --size 0.01
uv run python -m backtest.run --symbol BTC --bar-spec 1-HOUR-LAST --size 0.01
```

> **Hyperliquid candle cap:** the API serves only the most recent ~5000 candles per
> coin+interval (1m ≈ 3.5 days!). Requests older than that fail loudly unless you pass
> `--allow-truncated`. Full funding history IS available. Deep 1m perp history requires
> a live recorder (follow-up). There is no historical open-interest API.

## Backend commands

```bash
uv run ruff check                     # lint
uv run pytest                         # tests (in-memory SQLite from the ORM metadata)
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000   # API — localhost only
uv run python -m ingestion.ibkr ingest SPY --duration "1 Y"  # live daily-bar ingest
```

Quick API checks (incl. the research/registry endpoints):

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/meta
curl "http://127.0.0.1:8000/api/instruments/SPY/bars?timeframe=1d"
curl http://127.0.0.1:8000/api/backtest-runs
curl http://127.0.0.1:8000/api/cemetery      # killed hypotheses (§7.2)
```

## Front-end (optional)

```bash
cd frontend && npm install && npm run dev   # http://localhost:5173, proxies /api → :8000
```

The dev server proxies `/api` to the backend, so the browser only talks to localhost. The
TradingView attribution required by the Lightweight Charts license is rendered via the
`attributionLogo` option and the page footer — do not strip it.

## Notes & honest caveats

- **Read-only, live Gateway.** This host reads historical data from a live-account Gateway
  (port 4001); no orders are placed and live execution factories are not wired. Anything
  that could place an order must run against a paper endpoint first (CLAUDE.md §15).
- **Replication gate is red.** Proprietary hypotheses are off the table until the engine
  reproduces a public benchmark (CBOE PUT for the equity-vol track) — which needs options
  history not yet ingested. The MES run validates the engine plumbing only.
- **Tests vs production schema.** `pytest` builds an in-memory SQLite from the ORM metadata;
  the real schema lives in the Alembic migrations targeting Postgres, kept in sync by hand.
- **Stubs, flagged not hidden.** Historical vendors (`ingestion/vendors/`) and quality gates
  (`ingestion/quality/`) are package stubs; GEX compute (`compute/`) is a documented stub.
- **Verify APIs.** nautilus, `ib_async`, and Lightweight Charts signatures move between
  releases — verify against the installed version before relying on them.

## Layout

```
core/        # config (settings, dealer-sign), provenance (git SHA, config hash)
ingestion/   # persistence.py (shared §6.3 layer) + ibkr/ binance/ hyperliquid/
             # (live/backfill → Postgres), vendors/ + quality/ (stubs)
backtest/    # catalog/ engine/ costs/ strategies/ hypotheses/
             # + download_ib.py (IB → catalog), materialize.py (Postgres → catalog), run.py
api/         # FastAPI (bars, instruments, research) — localhost-bound
db/          # SQLAlchemy models + Alembic migrations (§9)
compute/     # GEX/walls — optional viz support (stub)
frontend/    # Vite + TS + Lightweight Charts v5 (optional)
```
