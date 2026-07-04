"""Ingest Hyperliquid perp candles into Postgres with provenance (§6.3).

The candleSnapshot API serves only the most recent ~5000 candles per
coin+interval. If the requested start predates what the API can serve, this
module FAILS LOUD by default: ingesting a silently truncated window would
record a partial history as if it were complete. `allow_truncated=True` is the
explicit operator override — it ingests the available window and logs the
actual range. Deep intraday perp history only exists if we record it live
(follow-up: WebSocket collector).
"""

from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from ingestion.hyperliquid.client import HyperliquidClient
from ingestion.persistence import (
    EmptyDataError,
    NormalizedBar,
    get_or_create_instrument,
    store_bars,
    today_vintage,
)

logger = logging.getLogger("lotus.ingestion.hyperliquid")

SOURCE = "HYPERLIQUID"
# Tolerance for "the first candle is later than requested": one interval of
# slack covers boundary alignment; anything beyond that is real truncation.
_INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
}


class TruncatedHistoryError(RuntimeError):
    """The API could not serve the full requested window (5000-candle cap)."""


def _normalize(candle: dict) -> NormalizedBar:
    """Candle {t,T,s,i,o,c,h,l,v,n} — t is open time ms; strings → Decimal."""
    return NormalizedBar(
        ts=dt.datetime.fromtimestamp(int(candle["t"]) / 1000, tz=dt.UTC),
        open=Decimal(candle["o"]),
        high=Decimal(candle["h"]),
        low=Decimal(candle["l"]),
        close=Decimal(candle["c"]),
        volume=Decimal(candle["v"]),
    )


def _drop_in_progress(candles: list[dict], now_ms: int) -> list[dict]:
    """Drop the still-forming candle (close time in the future) — §6.3."""
    closed = [c for c in candles if int(c["T"]) < now_ms]
    dropped = len(candles) - len(closed)
    if dropped:
        logger.info("dropped %s in-progress candle(s) — will land after close", dropped)
    return closed


def check_truncation(
    candles: list[dict], requested_start_ms: int, interval: str, allow_truncated: bool
) -> None:
    """Raise unless the response actually covers the requested start (§6.3)."""
    if not candles:
        return
    first_open_ms = int(candles[0]["t"])
    slack = _INTERVAL_MS.get(interval, 86_400_000)
    if first_open_ms > requested_start_ms + slack:
        earliest = dt.datetime.fromtimestamp(first_open_ms / 1000, tz=dt.UTC)
        if not allow_truncated:
            raise TruncatedHistoryError(
                f"Hyperliquid serves only the most recent ~5000 {interval} candles; "
                f"earliest available is {earliest.isoformat()} but "
                f"{dt.datetime.fromtimestamp(requested_start_ms / 1000, tz=dt.UTC).isoformat()} "
                f"was requested. Re-run with --allow-truncated to ingest the "
                f"available window explicitly."
            )
        logger.warning(
            "truncated history accepted (--allow-truncated): window starts %s, not %s",
            earliest.isoformat(),
            dt.datetime.fromtimestamp(requested_start_ms / 1000, tz=dt.UTC).isoformat(),
        )


async def ingest_bars(
    session: AsyncSession,
    coin: str,
    interval: str,
    start: dt.datetime,
    end: dt.datetime | None = None,
    *,
    allow_truncated: bool = False,
) -> int:
    """Backfill Hyperliquid perp bars. Idempotent; returns bars inserted."""
    end = end or dt.datetime.now(tz=dt.UTC)
    start_ms = int(start.timestamp() * 1000)
    now_ms = int(dt.datetime.now(tz=dt.UTC).timestamp() * 1000)

    async with HyperliquidClient() as client:
        await client.validate_coin(coin)
        raw = await client.fetch_candles(coin, interval, start_ms, int(end.timestamp() * 1000))

    check_truncation(raw, start_ms, interval, allow_truncated)
    raw = _drop_in_progress(raw, now_ms)
    if not raw:
        raise EmptyDataError(
            f"Hyperliquid returned no closed {interval} candles for {coin!r} in "
            f"{start.date()}..{end.date()}. Recording the gap, not filling it."
        )

    instrument = await get_or_create_instrument(
        session, coin, sec_type="PERP", exchange="HYPERLIQUID", currency="USDC"
    )
    inserted = await store_bars(
        session,
        instrument,
        [_normalize(c) for c in raw],
        timeframe=interval,
        source=SOURCE,
        vintage=today_vintage(),
    )
    await session.commit()
    logger.info(
        "Ingested %s %s: %s new bars (of %s closed returned)", coin, interval, inserted, len(raw)
    )
    return inserted
