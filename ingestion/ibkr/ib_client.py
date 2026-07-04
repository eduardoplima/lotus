"""Thin async wrapper around ib_async for Interactive Brokers connectivity.

API surface verified against current ib_async docs (do not invent methods, §14):
  * ``IB()`` / ``IB.connectAsync(host, port, clientId, timeout)`` — async connect.
  * ``Stock(symbol, exchange, currency)`` — contract construction.
  * ``IB.reqHistoricalDataAsync(contract, endDateTime, durationStr,
    barSizeSetting, whatToShow, useRTH)`` -> ``BarDataList`` whose rows expose
    ``.date/.open/.high/.low/.close/.volume``.
  * ``IB.disconnect()``.

Connection reality (§7): the session can drop (weekly reset, crashes). Every
connection state transition is logged, and ``connect`` is safe to call again to
re-establish. This is M0-level reconnect (reconnect on demand); robust
auto-reconnect/backoff is an M4 concern and intentionally not over-built here.
"""

from __future__ import annotations

import logging

from core.config import settings
from ib_async import IB, BarDataList, Stock

logger = logging.getLogger("lotus.ingestion.ib")


class IBClient:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
    ) -> None:
        self.host = host or settings.ib_host
        self.port = port or settings.ib_port
        self.client_id = client_id if client_id is not None else settings.ib_client_id
        self.ib = IB()

    async def connect(self, timeout: float = 8.0) -> None:  # noqa: ASYNC109 (mirrors ib_async API)
        if self.ib.isConnected():
            return
        logger.info("IB connecting -> %s:%s clientId=%s", self.host, self.port, self.client_id)
        await self.ib.connectAsync(
            host=self.host, port=self.port, clientId=self.client_id, timeout=timeout
        )
        logger.info("IB connected")

    def disconnect(self) -> None:
        if self.ib.isConnected():
            self.ib.disconnect()
            logger.info("IB disconnected")

    async def fetch_daily_bars(self, symbol: str, duration: str = "1 Y") -> BarDataList:
        """Fetch daily TRADES bars (RTH) for a US stock.

        Returns the raw BarDataList; persistence/validation is the caller's job.
        """
        contract = Stock(symbol.upper(), "SMART", "USD")
        logger.info("reqHistoricalData %s duration=%s barSize=1 day", symbol, duration)
        bars = await self.ib.reqHistoricalDataAsync(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
        )
        return bars

    async def __aenter__(self) -> IBClient:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.disconnect()
