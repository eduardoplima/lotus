"""IBKR preflight for the intraday-regime-momentum sprint (Phase 0).

Verifies, read-only:
  1. Gateway connectivity (env IB_HOST/IB_PORT/IB_CLIENT_ID — never hardcoded).
  2. One day of 5-minute TRADES bars for SPY (useRTH) and the front MES contract.
  3. Head timestamps (earliest available history) for both — these parameterize
     the registration's sample-period section.

API names verified against installed ib_async 2.1.0 (rule 7):
  * IB.connectAsync(host, port, clientId, timeout)
  * IB.qualifyContractsAsync(*contracts)
  * IB.reqHistoricalDataAsync(contract, endDateTime, durationStr, barSizeSetting,
        whatToShow, useRTH, ...) -> BarDataList
  * IB.reqHeadTimeStampAsync(contract, whatToShow, useRTH, formatDate) -> datetime
  * Stock(symbol, exchange, currency), ContFuture(symbol, exchange)

A market-data permission error STOPS the affected leg and is reported verbatim —
no silent substitution of another data source.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

from ib_async import IB, ContFuture, Stock

logger = logging.getLogger("lotus.research.preflight_ibkr")


async def preflight() -> dict:
    host = os.environ.get("IB_HOST", "127.0.0.1")
    port = int(os.environ.get("IB_PORT", "4001"))
    client_id = int(os.environ.get("IB_CLIENT_ID", "42"))

    result: dict = {"host": host, "port": port}
    ib = IB()
    await ib.connectAsync(host=host, port=port, clientId=client_id, timeout=15)
    result["connected"] = True

    spy = Stock("SPY", "SMART", "USD")
    mes = ContFuture("MES", "CME")
    qualified = await ib.qualifyContractsAsync(spy, mes)
    result["qualified"] = [f"{c.localSymbol or c.symbol} conId={c.conId}" for c in qualified]

    for label, contract, use_rth in (("SPY", spy, True), ("MES", mes, False)):
        leg: dict = {}
        try:
            bars = await ib.reqHistoricalDataAsync(
                contract,
                endDateTime="",
                durationStr="1 D",
                barSizeSetting="5 mins",
                whatToShow="TRADES",
                useRTH=use_rth,
            )
            leg["bars_1d"] = len(bars)
            if bars:
                leg["first_bar"] = str(bars[0].date)
                leg["last_bar"] = str(bars[-1].date)
                leg["last_close"] = bars[-1].close
            head = await ib.reqHeadTimeStampAsync(
                contract, whatToShow="TRADES", useRTH=use_rth, formatDate=1
            )
            leg["head_timestamp"] = str(head)
        except Exception as exc:  # noqa: BLE001 — report verbatim, per spec
            leg["error"] = f"{type(exc).__name__}: {exc}"
        result[label] = leg

    ib.disconnect()
    return result


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    try:
        result = asyncio.run(preflight())
    except (OSError, TimeoutError, ConnectionError) as exc:
        print(json.dumps({"connected": False, "error": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 3
    print(json.dumps(result, indent=2, default=str))
    blocked = [k for k in ("SPY", "MES") if "error" in result.get(k, {})]
    if blocked:
        print(f"\nBLOCKED LEGS: {blocked} — reported verbatim above.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
