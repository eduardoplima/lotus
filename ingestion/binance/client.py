"""Async Binance SPOT market-data client (public REST, no auth).

API surface verified against current docs (§14):
  * GET /api/v3/klines — symbol, interval, startTime/endTime (ms), limit<=1000;
    weight 2. Response rows: [openTime, o, h, l, c, volume, closeTime, ...]
    with prices as strings. History reaches back to the symbol's listing date;
    paginate by advancing startTime past the last closeTime.
  * GET /api/v3/exchangeInfo?symbol=... — weight 20; symbol metadata incl.
    quoteAsset and PRICE_FILTER/LOT_SIZE filters.

Rate hygiene: 6000 weight/min/IP. Every response carries X-MBX-USED-WEIGHT-1m;
we throttle before the cap. 429 → honor Retry-After with bounded backoff.
418 = IP ban for hammering after 429s → raise immediately, never retry.
451 = geo-block (US and other restricted regions) → raise with guidance.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from core.config import settings

logger = logging.getLogger("lotus.ingestion.binance")

KLINES_MAX_LIMIT = 1000
# Throttle threshold: stay well under the 6000/min IP cap.
WEIGHT_SOFT_LIMIT = 4800
MAX_RETRIES_429 = 5


class BinanceGeoBlockedError(RuntimeError):
    """HTTP 451 — this egress IP is geo-restricted by Binance (even read-only)."""


class BinanceBannedError(RuntimeError):
    """HTTP 418 — IP auto-banned for ignoring 429s. Do not retry."""


class BinanceClient:
    def __init__(
        self,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url or settings.binance_base_url,
            timeout=30.0,
            transport=transport,
        )

    async def __aenter__(self) -> BinanceClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._http.aclose()

    async def _get(self, path: str, params: dict) -> httpx.Response:
        for attempt in range(MAX_RETRIES_429 + 1):
            response = await self._http.get(path, params=params)

            if response.status_code == 451:
                raise BinanceGeoBlockedError(
                    "Binance returned 451 (geo-restricted IP). Public market data is "
                    "also blocked from restricted regions — run ingestion from a "
                    "non-restricted egress."
                )
            if response.status_code == 418:
                raise BinanceBannedError(
                    "Binance returned 418 (IP ban). Stop all requests and wait out "
                    f"the ban (Retry-After: {response.headers.get('Retry-After', '?')}s)."
                )
            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", "1"))
                delay = max(retry_after, 2**attempt)
                logger.warning("Binance 429 — backing off %.1fs (attempt %s)", delay, attempt + 1)
                await asyncio.sleep(delay)
                continue

            response.raise_for_status()

            used = int(response.headers.get("X-MBX-USED-WEIGHT-1m", "0"))
            if used >= WEIGHT_SOFT_LIMIT:
                # Sleep to the next minute boundary before the hard cap bites.
                logger.info("Binance weight %s/6000 — throttling 20s", used)
                await asyncio.sleep(20)
            return response

        raise RuntimeError(f"Binance still rate-limiting after {MAX_RETRIES_429} retries")

    async def fetch_exchange_info(self, symbol: str) -> dict:
        """Symbol metadata (quoteAsset, filters). Raises on unknown symbol."""
        response = await self._get("/api/v3/exchangeInfo", {"symbol": symbol.upper()})
        symbols = response.json().get("symbols", [])
        if not symbols:
            raise ValueError(f"Binance exchangeInfo returned no metadata for {symbol!r}")
        return symbols[0]

    async def fetch_klines(
        self,
        symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int | None = None,
        limit: int = KLINES_MAX_LIMIT,
    ) -> list[list]:
        params: dict = {
            "symbol": symbol.upper(),
            "interval": interval,
            "startTime": start_ms,
            "limit": limit,
        }
        if end_ms is not None:
            params["endTime"] = end_ms
        response = await self._get("/api/v3/klines", params)
        return response.json()

    async def fetch_klines_range(
        self, symbol: str, interval: str, start_ms: int, end_ms: int
    ) -> list[list]:
        """Paginate klines across [start_ms, end_ms], advancing past each page's
        last closeTime. Stops on a short page or when past end_ms."""
        out: list[list] = []
        cursor = start_ms
        while cursor < end_ms:
            page = await self.fetch_klines(symbol, interval, cursor, end_ms)
            if not page:
                break
            out.extend(page)
            last_close_ms = int(page[-1][6])
            cursor = last_close_ms + 1
            if len(page) < KLINES_MAX_LIMIT:
                break
        return out
