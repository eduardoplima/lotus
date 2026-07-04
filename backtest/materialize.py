"""Materialize Postgres bars into the nautilus ParquetDataCatalog (§2).

Postgres is the system of record; nautilus only reads the catalog. This module
is the ETL between them for the crypto sources:

    python -m backtest.materialize --symbol BTCUSDT --source BINANCE --timeframe 1h
    python -m backtest.materialize --symbol BTC --source HYPERLIQUID --timeframe 1h

Point-in-time discipline (§6.1): nautilus delivers bars at their CLOSE time,
while `ohlc_bar.ts` stores the OPEN time — so `ts_event`/`ts_init` here are
open + timeframe duration. Getting this wrong would hand the engine a bar
before it finished forming, i.e. lookahead.

Precisions are derived from the stored Decimals (max observed decimal places),
so Price/Quantity construction never silently rounds real data. Fees are set
pessimistically on the instrument (§6.4) and consumed by MakerTakerFeeModel.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import logging
import sys
from decimal import Decimal

from db.models import Instrument, OhlcBar
from db.session import get_sessionmaker
from nautilus_trader.model.currencies import USDC
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import CryptoPerpetual, CurrencyPair
from nautilus_trader.model.objects import Currency, Price, Quantity
from sqlalchemy import select

from backtest.catalog import get_catalog, write_bars, write_instruments

logger = logging.getLogger("lotus.backtest.materialize")

# Pessimistic taker fees (§6.4): worse than the standard public schedules.
TAKER_FEE = {"BINANCE": Decimal("0.0010"), "HYPERLIQUID": Decimal("0.0005")}

_TIMEFRAME_TO_BARSPEC = {"1m": "1-MINUTE", "1h": "1-HOUR", "1d": "1-DAY"}
_TIMEFRAME_TO_DELTA = {
    "1m": dt.timedelta(minutes=1),
    "1h": dt.timedelta(hours=1),
    "1d": dt.timedelta(days=1),
}


def _decimals(value: Decimal) -> int:
    exponent = value.normalize().as_tuple().exponent
    return max(0, -int(exponent))


def _max_precision(values: list[Decimal], cap: int = 9) -> int:
    """Max observed decimal places (nautilus fixed-point caps at 9 on this build)."""
    return min(cap, max((_decimals(v) for v in values), default=2))


def _base_asset(symbol: str, quote: str) -> str:
    if not symbol.endswith(quote):
        raise ValueError(
            f"cannot derive base asset: symbol {symbol!r} does not end with quote {quote!r}"
        )
    return symbol[: -len(quote)]


def build_nautilus_instrument(row: Instrument, bars: list[OhlcBar]):
    """Map a Postgres instrument row to a nautilus instrument definition."""
    if row.exchange not in TAKER_FEE:
        raise ValueError(f"no nautilus mapping for exchange {row.exchange!r}")
    prices = [Decimal(b.close) for b in bars]
    volumes = [Decimal(b.volume) for b in bars if b.volume is not None]
    price_precision = _max_precision(prices)
    size_precision = _max_precision(volumes) if volumes else 5
    price_increment = Price(Decimal(1).scaleb(-price_precision), price_precision)
    size_increment = Quantity(Decimal(1).scaleb(-size_precision), size_precision)
    taker = TAKER_FEE[row.exchange]

    if row.exchange == "BINANCE":
        quote = Currency.from_str(row.currency)
        base = Currency.from_str(_base_asset(row.symbol, row.currency))
        return CurrencyPair(
            instrument_id=InstrumentId.from_str(f"{row.symbol}.BINANCE"),
            raw_symbol=Symbol(row.symbol),
            base_currency=base,
            quote_currency=quote,
            price_precision=price_precision,
            size_precision=size_precision,
            price_increment=price_increment,
            size_increment=size_increment,
            ts_event=0,
            ts_init=0,
            maker_fee=taker,  # pessimistic: charge taker even on maker fills
            taker_fee=taker,
        )
    if row.exchange == "HYPERLIQUID":
        base = Currency.from_str(row.symbol)
        return CryptoPerpetual(
            instrument_id=InstrumentId.from_str(f"{row.symbol}-USDC-PERP.HYPERLIQUID"),
            raw_symbol=Symbol(row.symbol),
            base_currency=base,
            quote_currency=USDC,
            settlement_currency=USDC,
            is_inverse=False,
            price_precision=price_precision,
            size_precision=size_precision,
            price_increment=price_increment,
            size_increment=size_increment,
            ts_event=0,
            ts_init=0,
            maker_fee=taker,
            taker_fee=taker,
        )
    raise ValueError(f"no nautilus mapping for exchange {row.exchange!r}")


def build_nautilus_bars(instrument, rows: list[OhlcBar], timeframe: str) -> list[Bar]:
    """Postgres rows (open-time stamped) → nautilus Bars (close-time stamped)."""
    spec = _TIMEFRAME_TO_BARSPEC[timeframe]
    delta = _TIMEFRAME_TO_DELTA[timeframe]
    bar_type = BarType.from_str(f"{instrument.id}-{spec}-LAST-EXTERNAL")
    pp, sp = instrument.price_precision, instrument.size_precision

    bars = []
    for row in rows:
        close_ns = int((row.ts + delta).timestamp() * 1_000_000_000)
        bars.append(
            Bar(
                bar_type,
                Price(Decimal(row.open), pp),
                Price(Decimal(row.high), pp),
                Price(Decimal(row.low), pp),
                Price(Decimal(row.close), pp),
                Quantity(Decimal(row.volume or 0), sp),
                close_ns,  # ts_event = close time (§6.1)
                close_ns,
            )
        )
    return bars


async def materialize(symbol: str, source: str, timeframe: str, catalog_path: str | None) -> int:
    """Read bars from Postgres, write instrument + bars to the catalog."""
    async with get_sessionmaker()() as session:
        row = await session.scalar(
            select(Instrument).where(
                Instrument.symbol == symbol.upper(), Instrument.exchange == source
            )
        )
        if row is None:
            raise ValueError(
                f"no instrument {symbol!r} from {source!r} in Postgres — ingest it first."
            )
        result = await session.scalars(
            select(OhlcBar)
            .where(
                OhlcBar.instrument_id == row.id,
                OhlcBar.timeframe == timeframe,
                OhlcBar.source == source,
            )
            .order_by(OhlcBar.ts)
        )
        rows = list(result.all())

    if not rows:
        raise ValueError(
            f"no {timeframe} bars for {symbol!r}/{source} in Postgres — ingest them first."
        )

    instrument = build_nautilus_instrument(row, rows)
    bars = build_nautilus_bars(instrument, rows, timeframe)

    catalog = get_catalog(catalog_path)
    write_instruments(catalog, [instrument])
    write_bars(catalog, bars)
    logger.info("materialized %s: %s bars -> %s", instrument.id, len(bars), bars[0].bar_type)
    return len(bars)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    p = argparse.ArgumentParser(prog="python -m backtest.materialize")
    p.add_argument("--symbol", required=True)
    p.add_argument("--source", required=True, choices=["BINANCE", "HYPERLIQUID"])
    p.add_argument("--timeframe", default="1h", choices=sorted(_TIMEFRAME_TO_BARSPEC))
    p.add_argument("--catalog", default=None)
    args = p.parse_args(argv)

    try:
        n = asyncio.run(materialize(args.symbol, args.source, args.timeframe, args.catalog))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"materialized {n} {args.timeframe} bars for {args.symbol.upper()} ({args.source})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
