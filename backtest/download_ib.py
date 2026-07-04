"""Download historical futures bars from IBKR into the ParquetDataCatalog.

This is the backtest-side ingestion path: it uses nautilus_trader's own IB
adapter (`HistoricInteractiveBrokersClient`, built on `ibapi`) — distinct from
the live `ib_async` Postgres path in `ingestion/ibkr`. Both talk to the same
Gateway; this one only ever **reads** (§15).

Usage:
    python -m backtest.download_ib --symbol MES --expiry 202609 \
        --start 2025-01-01 --end 2025-06-30 --bar-spec 1-DAY-LAST

Fails loudly (§6.3) if IB returns no instrument or no bars — a hole is recorded,
never fabricated. A common cause of "no bars" is missing CME futures market-data
permission on the account; that surfaces as an explicit error, not silence.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import logging
import sys

from core.config import settings
from nautilus_trader.adapters.interactive_brokers.common import IBContract
from nautilus_trader.adapters.interactive_brokers.historical.client import (
    HistoricInteractiveBrokersClient,
)

from backtest.catalog import get_catalog, write_bars, write_instruments

logger = logging.getLogger("lotus.backtest.download_ib")

TZ = "America/New_York"


class NoDataError(RuntimeError):
    """IB returned no instrument or no bars — a hole to record, not to fill (§6.3)."""


def front_quarter(today: dt.date) -> str:
    """Return the nearest upcoming quarterly contract month as YYYYMM (Mar/Jun/Sep/Dec)."""
    for month in (3, 6, 9, 12):
        if month >= today.month:
            return f"{today.year}{month:02d}"
    return f"{today.year + 1}03"


async def download(
    symbol: str,
    expiry: str,
    start: dt.datetime,
    end: dt.datetime,
    bar_specs: list[str],
    exchange: str,
    port: int,
    client_id: int,
    catalog_path: str | None,
    use_rth: bool = True,
) -> tuple[int, int]:
    """Fetch instrument + bars and persist to the catalog. Returns (n_instruments, n_bars)."""
    client = HistoricInteractiveBrokersClient(
        host=settings.ib_host, port=port, client_id=client_id
    )
    await client.connect()
    await asyncio.sleep(2)  # let the connection settle before requests

    contract = IBContract(
        secType="FUT",
        exchange=exchange,
        symbol=symbol.upper(),
        lastTradeDateOrContractMonth=expiry,
    )

    instruments = await client.request_instruments(contracts=[contract])
    if not instruments:
        raise NoDataError(
            f"IB returned no instrument for {symbol} {expiry} on {exchange}. "
            f"Check the contract month and that it is a valid listed future."
        )
    inst = instruments[0]
    logger.info(
        "resolved %s -> id=%s multiplier=%s tick=%s",
        symbol,
        inst.id,
        inst.multiplier,
        inst.price_increment,
    )

    # Request bars by the already-resolved instrument id (in the provider cache
    # from request_instruments). Passing the raw IBContract again makes nautilus
    # re-parse it under simplified symbology, which fails for a bare futures spec.
    bars = await client.request_bars(
        bar_specifications=bar_specs,
        start_date_time=start,
        end_date_time=end,
        tz_name=TZ,
        instrument_ids=[str(inst.id)],
        use_rth=use_rth,
        timeout=120,
    )
    if not bars:
        raise NoDataError(
            f"IB returned no bars for {symbol} {expiry} {bar_specs} in "
            f"{start.date()}..{end.date()}. Recording the gap, not filling it. "
            f"A likely cause is missing CME futures market-data permission."
        )

    catalog = get_catalog(catalog_path)
    write_instruments(catalog, instruments)
    write_bars(catalog, bars)
    logger.info("wrote %s instrument(s) and %s bar(s) to the catalog", len(instruments), len(bars))
    return len(instruments), len(bars)


def _parse_date(s: str) -> dt.datetime:
    return dt.datetime.strptime(s, "%Y-%m-%d")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    p = argparse.ArgumentParser(prog="python -m backtest.download_ib")
    p.add_argument("--symbol", default="MES")
    p.add_argument("--exchange", default="CME")
    p.add_argument("--expiry", default=None, help="Contract month YYYYMM (default: front quarter)")
    p.add_argument("--start", type=_parse_date, required=True, help="YYYY-MM-DD")
    p.add_argument("--end", type=_parse_date, required=True, help="YYYY-MM-DD")
    p.add_argument("--bar-spec", dest="bar_specs", action="append", help="e.g. 1-DAY-LAST")
    p.add_argument("--port", type=int, default=settings.ib_port)
    p.add_argument("--client-id", type=int, default=settings.ib_client_id + 10)
    p.add_argument("--catalog", default=None)
    p.add_argument(
        "--no-rth",
        dest="use_rth",
        action="store_false",
        help="Include electronic/overnight session, not just Regular Trading Hours",
    )
    args = p.parse_args(argv)

    expiry = args.expiry or front_quarter(args.end.date())
    bar_specs = args.bar_specs or ["1-DAY-LAST"]

    try:
        n_inst, n_bars = asyncio.run(
            download(
                symbol=args.symbol,
                expiry=expiry,
                start=args.start,
                end=args.end,
                bar_specs=bar_specs,
                exchange=args.exchange,
                port=args.port,
                client_id=args.client_id,
                catalog_path=args.catalog,
                use_rth=args.use_rth,
            )
        )
    except NoDataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (OSError, TimeoutError) as exc:
        print(
            f"error: could not reach / complete request against IB Gateway at "
            f"{settings.ib_host}:{args.port} ({exc}).",
            file=sys.stderr,
        )
        return 3

    print(
        f"downloaded {args.symbol} {expiry}: {n_inst} instrument(s), {n_bars} bar(s) "
        f"({bar_specs}) -> catalog"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
