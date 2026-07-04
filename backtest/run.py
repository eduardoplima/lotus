"""Run a backtest end-to-end and record it reproducibly (§6.3, §7.5).

Reads MES bars from the ParquetDataCatalog, runs the SMA-cross plumbing strategy
under a pessimistic cost model, prints headline **and** tail/drawdown metrics
(never averages alone — the tail is the whole story for convex strategies), and
writes a `backtest_run` (git SHA, data window, cost model) + `backtest_result`
row to Postgres so the run is traceable and not double-counted.

    python -m backtest.run --symbol MES --bar-spec 1-DAY-LAST

NOTE: the SMA strategy is an engine-plumbing validation, not a pre-registered or
proprietary hypothesis (§7.3/§14). `hypothesis_id` is left null and the result is
labeled a validation run — it must not be read as a discovery.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import logging
import sys

from core.provenance import config_hash, git_sha
from db.models import BacktestResult, BacktestRun
from db.session import get_sessionmaker
from nautilus_trader.model.data import BarType
from sqlalchemy.exc import IntegrityError

from backtest.catalog import get_catalog
from backtest.costs import DEFAULT_COST_MODEL
from backtest.engine import build_engine

logger = logging.getLogger("lotus.backtest.run")


def _ns_to_iso(ns: int) -> str:
    return dt.datetime.fromtimestamp(ns / 1e9, tz=dt.UTC).isoformat()


def _json_safe(value):
    """Recursively replace NaN/inf with None — Postgres JSON rejects them.
    A metric that does not exist is honestly null, not a fake number."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    return value


def _max_drawdown(equity: list[float]) -> float:
    """Max peak-to-trough drawdown of an equity curve, as a negative fraction."""
    peak = equity[0]
    worst = 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            worst = min(worst, (v - peak) / peak)
    return worst


def _tail_metrics(engine, starting_balance: float) -> dict:
    """Compute drawdown/worst-trade from the closed-positions report (defensive)."""
    try:
        report = engine.trader.generate_positions_report()
    except Exception as exc:  # noqa: BLE001 — report shape can vary; degrade honestly
        return {"note": f"positions report unavailable: {exc}"}
    if report is None or len(report) == 0:
        return {"n_closed_positions": 0, "note": "no closed positions — nothing to draw down"}

    def _num(x) -> float:
        # realized_pnl may be a Money-like string "123.45 USD" or a number.
        s = str(x).split(" ")[0].replace(",", "")
        try:
            return float(s)
        except ValueError:
            return 0.0

    col = "realized_pnl" if "realized_pnl" in report.columns else None
    if col is None:
        return {"n_closed_positions": int(len(report)), "note": "no realized_pnl column"}

    pnls = [_num(v) for v in report[col].tolist()]
    equity = [starting_balance]
    for p in pnls:
        equity.append(equity[-1] + p)
    return {
        "n_closed_positions": len(pnls),
        "worst_trade_pnl": min(pnls) if pnls else 0.0,
        "max_drawdown_frac": round(_max_drawdown(equity), 6),
        "final_equity": round(equity[-1], 2),
    }


def _stress_coverage(start_iso: str, end_iso: str) -> dict:
    """Record which §7.4 stress windows the data window covers — honest wiring."""
    from backtest.hypotheses import STRESS_WINDOWS

    start, end = start_iso[:10], end_iso[:10]
    out = {}
    for name, (w_start, w_end) in STRESS_WINDOWS.items():
        covered = not (end < w_start or start > w_end)
        out[name] = "covered" if covered else "not_covered"
    return out


class _PersistStatus:
    """Outcome of the persistence attempt, so the report can be honest."""

    def __init__(self, run_id: int | None, note: str) -> None:
        self.run_id = run_id
        self.note = note


async def _persist(run_row: BacktestRun, result_payload: dict) -> _PersistStatus:
    """Write run + result to Postgres. Degrade loudly (§6.5) if the DB is down —
    the backtest itself still succeeds; we never silently pretend it persisted."""
    try:
        async with get_sessionmaker()() as session:
            session.add(run_row)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                return _PersistStatus(None, "duplicate config — not re-recorded")
            session.add(BacktestResult(run_id=run_row.id, **result_payload))
            await session.commit()
            return _PersistStatus(run_row.id, f"backtest_run id={run_row.id}")
    except (OSError, ConnectionError) as exc:
        logger.warning("Postgres unreachable — provenance NOT persisted: %s", exc)
        return _PersistStatus(None, f"NOT PERSISTED (Postgres unreachable: {type(exc).__name__})")
    except Exception as exc:  # noqa: BLE001 — asyncpg wraps connection errors variously
        logger.warning("persistence failed — provenance NOT written: %s", exc)
        return _PersistStatus(None, f"NOT PERSISTED ({type(exc).__name__})")


def _match_instrument(instruments, symbol: str):
    """Resolve a user symbol against catalog instrument ids, strictly.

    Exact symbol-part match first (BTCUSDT → BTCUSDT.BINANCE), then a
    boundary-delimited prefix (BTC → BTC-USDC-PERP.HYPERLIQUID). Ambiguity or
    no match returns None — the caller reports candidates, never guesses.
    """
    sym = symbol.upper()
    # The catalog may hold duplicate definitions of one instrument (re-downloads
    # append) — dedupe by id before matching.
    instruments = list({str(i.id): i for i in instruments}.values())
    exact = [i for i in instruments if str(i.id).split(".")[0] == sym]
    if len(exact) == 1:
        return exact[0]
    boundary = [
        i
        for i in instruments
        if str(i.id).startswith(sym) and not str(i.id)[len(sym) : len(sym) + 1].isalnum()
    ]
    if len(boundary) == 1:
        return boundary[0]
    return None


def run(args: argparse.Namespace) -> int:
    catalog = get_catalog(args.catalog)
    instruments = catalog.instruments()
    if not instruments:
        print(
            "error: catalog is empty — run `python -m backtest.download_ib` "
            "or `python -m backtest.materialize` first.",
            file=sys.stderr,
        )
        return 2

    inst = _match_instrument(instruments, args.symbol)
    if inst is None:
        ids = ", ".join(str(i.id) for i in instruments)
        print(
            f"error: no unambiguous instrument for {args.symbol!r}. In catalog: {ids}",
            file=sys.stderr,
        )
        return 2
    bar_type = BarType.from_str(f"{inst.id}-{args.bar_spec}-EXTERNAL")
    bars = catalog.bars(bar_types=[str(bar_type)])
    if not bars:
        print(f"error: no bars for {bar_type} in catalog. Download them first.", file=sys.stderr)
        return 2

    cost = DEFAULT_COST_MODEL
    engine = build_engine(
        inst,
        bars,
        cost_model=cost,
        starting_balance=args.balance,
        fast_period=args.fast,
        slow_period=args.slow,
        trade_size=args.size,
    )
    engine.run()

    nautilus_result = engine.get_result()
    start_iso, end_iso = _ns_to_iso(bars[0].ts_event), _ns_to_iso(bars[-1].ts_event)

    headline = {
        "strategy": "sma_cross",
        "run_kind": "engine_validation",  # NOT a proprietary/pre-registered result (§14)
        "total_orders": nautilus_result.total_orders,
        "total_positions": nautilus_result.total_positions,
        "stats_pnls": nautilus_result.stats_pnls,
        "stats_returns": nautilus_result.stats_returns,
    }
    tail = _tail_metrics(engine, args.balance)
    stress = _stress_coverage(start_iso, end_iso)

    data_window = {
        "symbol": args.symbol.upper(),
        "instrument_id": str(inst.id),
        "start": start_iso,
        "end": end_iso,
        "n_bars": len(bars),
        "bar_spec": args.bar_spec,
        "source": "IBKR",
        "vintage": dt.datetime.now(tz=dt.UTC).date().isoformat(),
    }
    params = {
        "fast": args.fast,
        "slow": args.slow,
        "trade_size": args.size,
        "balance": args.balance,
    }
    code_version = git_sha()
    cost_dict = cost.to_dict()
    inst_taker = getattr(inst, "taker_fee", None)
    if inst_taker:
        # Crypto venues charge percentage fees carried on the instrument
        # (MakerTakerFeeModel), not the per-contract commission — record the
        # cost model that actually applied (§6.3).
        cost_dict["commission_model"] = "maker_taker_on_instrument"
        cost_dict["taker_fee"] = str(inst_taker)
        del cost_dict["commission_per_contract_usd"]

    run_row = BacktestRun(
        hypothesis_id=None,  # validation run — no pre-registered hypothesis (§7.3)
        strategy="sma_cross",
        params=params,
        data_window=data_window,
        cost_model=cost_dict,
        code_version=code_version,
        config_hash=config_hash("sma_cross", params, data_window, cost_dict, code_version),
    )
    result_payload = _json_safe({"headline": headline, "stress_windows": stress, "tail": tail})

    persist_status = asyncio.run(_persist(run_row, result_payload))

    # --- report (§7.5: tail is first-class, never hidden) ---
    print("=" * 68)
    print(f"Lotus backtest — sma_cross on {inst.id}  [ENGINE VALIDATION, not a discovery]")
    print(
        f"  data window : {start_iso[:10]} .. {end_iso[:10]}  "
        f"({len(bars)} bars, {args.bar_spec})"
    )
    print(f"  code version: {code_version}")
    fee_desc = (
        f"taker fee {inst_taker} (on instrument)"
        if inst_taker
        else f"${cost.commission_per_contract}/contract"
    )
    print(f"  cost model  : {fee_desc}, slip prob={cost.prob_slippage} (pessimistic)")
    print(f"  orders/positions: {headline['total_orders']} / {headline['total_positions']}")
    print(f"  PnL stats  : {nautilus_result.stats_pnls}")
    print(f"  return stats: {nautilus_result.stats_returns}")
    print(f"  TAIL       : {tail}")
    print(f"  stress cov : {stress}")
    print(f"  persisted  : {persist_status.note}")
    print("=" * 68)
    engine.dispose()
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    p = argparse.ArgumentParser(prog="python -m backtest.run")
    p.add_argument("--symbol", default="MES")
    p.add_argument("--bar-spec", default="1-DAY-LAST")
    p.add_argument("--fast", type=int, default=10)
    p.add_argument("--slow", type=int, default=30)
    p.add_argument("--balance", type=float, default=100_000.0)
    p.add_argument(
        "--size", default="1", help="Order size as decimal string, e.g. 0.01 for spot BTC"
    )
    p.add_argument("--catalog", default=None)
    return run(p.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
