"""Async Hyperliquid market-data client (public info API, no auth).

API surface verified against current docs (§14) — single endpoint
POST {base}/info, JSON body dispatched by "type":
  * candleSnapshot {req:{coin, interval, startTime, endTime}} →
    [{t,T,s,i,o,c,h,l,v,n}], strings. HARD CAP: only the most recent ~5000
    candles per coin+interval are served; there is NO paging further back.
  * fundingHistory {coin, startTime, endTime} → [{coin, fundingRate, premium,
    time}], max 500 rows per call; paginates to inception via last time + 1.
  * meta → {universe: [{name, szDecimals, maxLeverage, ...}]}.

Rate hygiene: 1200 weight/min/IP. candleSnapshot and fundingHistory cost 20
each plus a per-row surcharge (+1 per 60 candles / +1 per 20 funding rows).
We keep a client-side rolling 60s budget and back off on 429.
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx
from core.config import settings

logger = logging.getLogger("lotus.ingestion.hyperliquid")

FUNDING_PAGE_SIZE = 500
WEIGHT_BUDGET_PER_MIN = 1000  # of the 1200 hard cap
MAX_RETRIES_429 = 5


class UnknownCoinError(ValueError):
    """Coin not present in the perp universe — fail loud, not empty (§6.3)."""


class HyperliquidClient:
    def __init__(
        self,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url or settings.hyperliquid_base_url,
            timeout=30.0,
            transport=transport,
        )
        self._weight_events: list[tuple[float, int]] = []  # (monotonic ts, weight)

    async def __aenter__(self) -> HyperliquidClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._http.aclose()

    def _spend_weight(self, weight: int) -> float:
        """Record spend; return seconds to sleep if the rolling budget is hot."""
        now = time.monotonic()
        self._weight_events = [(t, w) for t, w in self._weight_events if now - t < 60]
        used = sum(w for _, w in self._weight_events)
        self._weight_events.append((now, weight))
        if used + weight >= WEIGHT_BUDGET_PER_MIN:
            oldest = self._weight_events[0][0]
            return max(0.0, 60 - (now - oldest))
        return 0.0

    async def _info(self, payload: dict, *, weight: int) -> httpx.Response:
        sleep_s = self._spend_weight(weight)
        if sleep_s > 0:
            logger.info("Hyperliquid weight budget hot — throttling %.1fs", sleep_s)
            await asyncio.sleep(sleep_s)

        for attempt in range(MAX_RETRIES_429 + 1):
            response = await self._http.post("/info", json=payload)
            if response.status_code == 429:
                delay = float(response.headers.get("Retry-After", 2**attempt))
                logger.warning(
                    "Hyperliquid 429 — backing off %.1fs (attempt %s)", delay, attempt + 1
                )
                await asyncio.sleep(delay)
                continue
            response.raise_for_status()
            return response

        raise RuntimeError(f"Hyperliquid still rate-limiting after {MAX_RETRIES_429} retries")

    async def fetch_meta(self) -> dict:
        response = await self._info({"type": "meta"}, weight=20)
        return response.json()

    async def validate_coin(self, coin: str) -> None:
        """Fail loud on a coin absent from the perp universe (typos return empty
        data downstream otherwise, which would masquerade as a data gap)."""
        meta = await self.fetch_meta()
        names = {asset["name"] for asset in meta.get("universe", [])}
        if coin not in names:
            raise UnknownCoinError(
                f"{coin!r} is not in the Hyperliquid perp universe "
                f"({len(names)} assets). Check the coin name (case-sensitive)."
            )

    async def fetch_candles(
        self, coin: str, interval: str, start_ms: int, end_ms: int
    ) -> list[dict]:
        """One candleSnapshot call. No pagination exists — the API serves at
        most the ~5000 most recent candles per coin+interval."""
        payload = {
            "type": "candleSnapshot",
            "req": {"coin": coin, "interval": interval, "startTime": start_ms, "endTime": end_ms},
        }
        # weight 20 + up to ~84 surcharge for a full 5000-candle response.
        response = await self._info(payload, weight=104)
        return response.json()

    async def fetch_funding_history(
        self, coin: str, start_ms: int, end_ms: int
    ) -> list[dict]:
        """Paginate fundingHistory (500 rows/call) across [start_ms, end_ms]."""
        out: list[dict] = []
        cursor = start_ms
        while cursor < end_ms:
            payload = {
                "type": "fundingHistory",
                "coin": coin,
                "startTime": cursor,
                "endTime": end_ms,
            }
            response = await self._info(payload, weight=45)  # 20 + 500/20 surcharge
            page = response.json()
            if not page:
                break
            out.extend(page)
            cursor = int(page[-1]["time"]) + 1
            if len(page) < FUNDING_PAGE_SIZE:
                break
        return out
