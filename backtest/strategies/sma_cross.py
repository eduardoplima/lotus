"""A trivial SMA-cross long/flat strategy.

PURPOSE: this is an **engine-plumbing validation**, not a registered or
proprietary hypothesis (§7/§14). It exists to prove the nautilus data path,
cost model, and result accounting end-to-end on real MES bars — nothing about
its P&L should be read as evidence of an edge. No pre-registration, so it must
never be presented as a discovery.

Logic: go long one contract when the fast SMA crosses above the slow SMA; flatten
when it crosses back below. Long/flat only, single contract, market orders.
"""

from __future__ import annotations

from decimal import Decimal

from nautilus_trader.indicators.averages import SimpleMovingAverage
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.trading.strategy import Strategy, StrategyConfig


class SmaCrossConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    fast_period: int = 10
    slow_period: int = 30
    # Decimal string so fractional sizes work for crypto spot (e.g. "0.01" BTC);
    # futures keep the "1"-contract default.
    trade_size: str = "1"


class SmaCross(Strategy):
    def __init__(self, config: SmaCrossConfig) -> None:
        super().__init__(config)
        self.fast = SimpleMovingAverage(config.fast_period)
        self.slow = SimpleMovingAverage(config.slow_period)
        self._was_fast_above: bool | None = None

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            raise RuntimeError(f"instrument {self.config.instrument_id} not in cache")
        self.register_indicator_for_bars(self.config.bar_type, self.fast)
        self.register_indicator_for_bars(self.config.bar_type, self.slow)
        self.subscribe_bars(self.config.bar_type)

    def on_bar(self, bar: Bar) -> None:
        if not (self.fast.initialized and self.slow.initialized):
            return

        fast_above = self.fast.value > self.slow.value
        # Skip the very first comparison (no prior state → no cross detected yet).
        if self._was_fast_above is None:
            self._was_fast_above = fast_above
            return

        crossed_up = fast_above and not self._was_fast_above
        crossed_down = not fast_above and self._was_fast_above
        self._was_fast_above = fast_above

        if crossed_up and self.portfolio.is_flat(self.config.instrument_id):
            self._market(OrderSide.BUY)
        elif crossed_down and not self.portfolio.is_flat(self.config.instrument_id):
            self.close_all_positions(self.config.instrument_id)

    def on_stop(self) -> None:
        self.close_all_positions(self.config.instrument_id)

    def _market(self, side: OrderSide) -> None:
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=side,
            # make_qty applies the instrument's size precision — a mismatched
            # precision is rejected by the matching engine.
            quantity=self.instrument.make_qty(Decimal(self.config.trade_size)),
        )
        self.submit_order(order)
