"""Postgres → nautilus catalog materialization: instrument mapping + close-time
stamping (§6.1 — a bar delivered before it closes is lookahead)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from backtest.materialize import build_nautilus_bars, build_nautilus_instrument
from db.models import Instrument, OhlcBar
from nautilus_trader.model.instruments import CryptoPerpetual, CurrencyPair


def _row(symbol: str, exchange: str, currency: str, sec_type: str) -> Instrument:
    return Instrument(symbol=symbol, sec_type=sec_type, exchange=exchange, currency=currency)


def _bar(ts: dt.datetime, close: str = "65000.53") -> OhlcBar:
    return OhlcBar(
        ts=ts,
        timeframe="1h",
        open=Decimal("64900.00"),
        high=Decimal("65100.00"),
        low=Decimal("64800.00"),
        close=Decimal(close),
        volume=Decimal("12.34567"),
        source="BINANCE",
        vintage="2026-07-03",
    )


def test_binance_maps_to_currency_pair_with_pessimistic_fee() -> None:
    row = _row("BTCUSDT", "BINANCE", "USDT", "CRYPTO")
    bars = [_bar(dt.datetime(2026, 7, 1, tzinfo=dt.UTC))]
    inst = build_nautilus_instrument(row, bars)
    assert isinstance(inst, CurrencyPair)
    assert str(inst.id) == "BTCUSDT.BINANCE"
    assert inst.base_currency.code == "BTC" and inst.quote_currency.code == "USDT"
    assert inst.taker_fee == Decimal("0.0010")  # pessimistic (§6.4)


def test_hyperliquid_maps_to_crypto_perpetual() -> None:
    row = _row("BTC", "HYPERLIQUID", "USDC", "PERP")
    bars = [_bar(dt.datetime(2026, 7, 1, tzinfo=dt.UTC))]
    inst = build_nautilus_instrument(row, bars)
    assert isinstance(inst, CryptoPerpetual)
    assert str(inst.id) == "BTC-USDC-PERP.HYPERLIQUID"
    assert inst.settlement_currency.code == "USDC"


def test_bars_are_stamped_at_close_time() -> None:
    row = _row("BTCUSDT", "BINANCE", "USDT", "CRYPTO")
    open_ts = dt.datetime(2026, 7, 1, 10, tzinfo=dt.UTC)
    rows = [_bar(open_ts)]
    inst = build_nautilus_instrument(row, rows)
    bars = build_nautilus_bars(inst, rows, "1h")

    close_ns = int((open_ts + dt.timedelta(hours=1)).timestamp() * 1_000_000_000)
    assert bars[0].ts_event == close_ns  # close, NOT open (§6.1)
    assert bars[0].ts_init == close_ns
    assert str(bars[0].bar_type) == "BTCUSDT.BINANCE-1-HOUR-LAST-EXTERNAL"
    assert str(bars[0].close) == "65000.53"


def test_unknown_exchange_raises() -> None:
    row = _row("XYZ", "KRAKEN", "USD", "CRYPTO")
    with pytest.raises(ValueError):
        build_nautilus_instrument(row, [_bar(dt.datetime(2026, 7, 1, tzinfo=dt.UTC))])
