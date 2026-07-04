"""Binance client: parsing, pagination, rate-limit behavior (mocked httpx)."""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

import httpx
import pytest
from ingestion.binance.bars import _drop_in_progress, _normalize
from ingestion.binance.client import (
    BinanceBannedError,
    BinanceClient,
    BinanceGeoBlockedError,
)

_NOW_MS = int(dt.datetime(2026, 7, 3, tzinfo=dt.UTC).timestamp() * 1000)
_HOUR_MS = 3_600_000


def _kline(open_ms: int, price: str = "100.5") -> list:
    return [
        open_ms,
        price,
        "101.0",
        "99.0",
        price,
        "12.34567890",
        open_ms + _HOUR_MS - 1,
        "0",
        10,
        "0",
        "0",
        "0",
    ]


def test_normalize_parses_strings_to_decimal() -> None:
    bar = _normalize(_kline(_NOW_MS, "0.000001234567"))
    assert bar.open == Decimal("0.000001234567")  # no float round-trip
    assert bar.volume == Decimal("12.34567890")
    assert bar.ts == dt.datetime(2026, 7, 3, tzinfo=dt.UTC)


def test_drop_in_progress_removes_open_kline() -> None:
    closed = _kline(_NOW_MS - 2 * _HOUR_MS)
    in_progress = _kline(_NOW_MS - _HOUR_MS + 1)  # closes after "now"
    kept = _drop_in_progress([closed, in_progress], _NOW_MS)
    assert kept == [closed]


async def test_pagination_advances_past_close_time() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        start = int(dict(request.url.params)["startTime"])
        calls.append(start)
        if len(calls) == 1:
            page = [_kline(start + i * _HOUR_MS) for i in range(1000)]
        else:
            page = [_kline(start)]  # short page → stop
        return httpx.Response(200, json=page, headers={"X-MBX-USED-WEIGHT-1m": "10"})

    async with BinanceClient(transport=httpx.MockTransport(handler)) as client:
        out = await client.fetch_klines_range("BTCUSDT", "1h", 0, 2000 * _HOUR_MS)

    assert len(out) == 1001
    # second call started right after the first page's last closeTime
    assert calls[1] == 999 * _HOUR_MS + _HOUR_MS - 1 + 1


async def test_429_retried_then_succeeds() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json=[], headers={"X-MBX-USED-WEIGHT-1m": "10"})

    async with BinanceClient(transport=httpx.MockTransport(handler)) as client:
        out = await client.fetch_klines("BTCUSDT", "1h", 0)
    assert out == [] and attempts["n"] == 2


async def test_418_raises_immediately() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(418, headers={"Retry-After": "120"})

    async with BinanceClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(BinanceBannedError):
            await client.fetch_klines("BTCUSDT", "1h", 0)


async def test_451_raises_geo_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(451)

    async with BinanceClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(BinanceGeoBlockedError):
            await client.fetch_klines("BTCUSDT", "1h", 0)


async def test_exchange_info_unknown_symbol_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=json.dumps({"symbols": []}), headers={"X-MBX-USED-WEIGHT-1m": "20"}
        )

    async with BinanceClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError):
            await client.fetch_exchange_info("NOPEUSDT")
