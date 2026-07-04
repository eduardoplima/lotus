"""Hyperliquid client: parsing, funding pagination, truncation policy (mocked httpx)."""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

import httpx
import pytest
from ingestion.hyperliquid.bars import (
    TruncatedHistoryError,
    _normalize,
    check_truncation,
)
from ingestion.hyperliquid.client import (
    FUNDING_PAGE_SIZE,
    HyperliquidClient,
    UnknownCoinError,
)

_NOW_MS = int(dt.datetime(2026, 7, 3, tzinfo=dt.UTC).timestamp() * 1000)
_HOUR_MS = 3_600_000


def _candle(open_ms: int) -> dict:
    return {
        "t": open_ms,
        "T": open_ms + _HOUR_MS - 1,
        "s": "BTC",
        "i": "1h",
        "o": "65000.5",
        "c": "65100.0",
        "h": "65200.0",
        "l": "64900.0",
        "v": "123.4567",
        "n": 42,
    }


def test_normalize_candle_to_decimal() -> None:
    bar = _normalize(_candle(_NOW_MS))
    assert bar.open == Decimal("65000.5")
    assert bar.volume == Decimal("123.4567")
    assert bar.ts == dt.datetime(2026, 7, 3, tzinfo=dt.UTC)


def test_truncation_raises_by_default() -> None:
    # requested from 0, but earliest served candle is much later
    candles = [_candle(_NOW_MS - 10 * _HOUR_MS)]
    with pytest.raises(TruncatedHistoryError):
        check_truncation(candles, 0, "1h", allow_truncated=False)


def test_truncation_allowed_with_flag() -> None:
    candles = [_candle(_NOW_MS - 10 * _HOUR_MS)]
    check_truncation(candles, 0, "1h", allow_truncated=True)  # no raise


def test_no_truncation_within_slack() -> None:
    start = _NOW_MS - 10 * _HOUR_MS
    candles = [_candle(start)]  # first candle == requested start
    check_truncation(candles, start, "1h", allow_truncated=False)  # no raise


async def test_funding_pagination_across_page_boundary() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["type"] == "fundingHistory"
        start = payload["startTime"]
        calls.append(start)
        if len(calls) == 1:
            page = [
                {"coin": "BTC", "fundingRate": "0.0000125", "premium": "0.0001", "time": start + i}
                for i in range(FUNDING_PAGE_SIZE)
            ]
        else:
            page = [
                {"coin": "BTC", "fundingRate": "-0.000003", "premium": None, "time": start}
            ]
        return httpx.Response(200, json=page)

    async with HyperliquidClient(transport=httpx.MockTransport(handler)) as client:
        out = await client.fetch_funding_history("BTC", 1000, 10_000_000)

    assert len(out) == FUNDING_PAGE_SIZE + 1
    assert calls[1] == 1000 + FUNDING_PAGE_SIZE - 1 + 1  # last time + 1


async def test_unknown_coin_fails_loud() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["type"] == "meta"
        return httpx.Response(200, json={"universe": [{"name": "BTC"}, {"name": "ETH"}]})

    async with HyperliquidClient(transport=httpx.MockTransport(handler)) as client:
        await client.validate_coin("BTC")  # ok
        with pytest.raises(UnknownCoinError):
            await client.validate_coin("btc")  # case-sensitive → fail loud
