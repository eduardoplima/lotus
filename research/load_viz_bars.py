"""One-shot: materialize curated sprint Parquet into Postgres ohlc_bar (1h/1d).

Resamples the immutable curated 5m series (data/curated/*) to 1h and 1d bars so
the viz layer (/api/bars) can serve real history for SPY, MES, BTCUSDT and the
BTC perp. Aggregation of real bars — o/h/l/c = first/max/min/last, volume = sum;
empty buckets are DROPPED, never filled (§6.3). Idempotent via the shared
insert-only store. Vintage = the curated acquisition date (2026-07-04), when
this data was actually captured — not today.
"""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd
from db.session import get_sessionmaker
from ingestion.persistence import NormalizedBar, get_or_create_instrument, store_bars

CURATED = Path("data/curated")
VINTAGE = "2026-07-04"  # acquisition date of the curated series (see ACQUIRED_AT / QA)

SPECS = [
    # (parquet, symbol, sec_type, exchange, currency, source)
    ("ibkr/SPY_5m.parquet", "SPY", "STK", "SMART", "USD", "IBKR"),
    ("ibkr/MES_STITCHED_5m.parquet", "MES", "FUT", "CME", "USD", "IBKR"),
    ("binance/BTCUSDT_5m.parquet", "BTCUSDT", "CRYPTO", "BINANCE", "USDT", "BINANCE"),
]

RULES = {"1h": "1h", "1d": "1D"}


def resample(bars: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = bars.resample(rule).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    return agg.dropna(subset=["open", "close"])  # drop empty buckets — record the hole


def to_normalized(df: pd.DataFrame) -> list[NormalizedBar]:
    out = []
    for ts, row in df.iterrows():
        out.append(
            NormalizedBar(
                ts=ts.to_pydatetime(),
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=Decimal(str(row["volume"])) if pd.notna(row["volume"]) else None,
            )
        )
    return out


async def main() -> int:
    async with get_sessionmaker()() as session:
        for parquet, symbol, sec_type, exchange, currency, source in SPECS:
            bars5 = pd.read_parquet(CURATED / parquet)[
                ["open", "high", "low", "close", "volume"]
            ]
            instrument = await get_or_create_instrument(
                session, symbol, sec_type=sec_type, exchange=exchange, currency=currency
            )
            for timeframe, rule in RULES.items():
                df = resample(bars5, rule)
                inserted = await store_bars(
                    session,
                    instrument,
                    to_normalized(df),
                    timeframe=timeframe,
                    source=source,
                    vintage=VINTAGE,
                )
                print(f"{symbol} {timeframe}: {inserted} inserted ({len(df)} resampled)")
        await session.commit()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
