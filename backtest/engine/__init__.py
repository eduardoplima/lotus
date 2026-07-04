"""nautilus_trader BacktestEngine wiring (§2, §6.4).

Builds a deterministic, timestamp-ordered backtest for a single instrument read
from the ParquetDataCatalog, with a pessimistic fill + fee model attached to
the venue. The engine only ever sees data as of the current event time — no
lookahead is possible within the engine (§6.1) — but that guarantee is only as
good as the `ts_event` on the loaded bars.

Venue config is derived from the instrument class:
  * FuturesContract      → MARGIN account in USD, per-contract commission
                           (backtest/costs pessimistic model).
  * CurrencyPair (spot)  → CASH account funded in the quote currency,
                           MakerTakerFeeModel (fees carried on the instrument,
                           set pessimistically at materialization).
  * CryptoPerpetual      → MARGIN account funded in the settlement currency,
                           MakerTakerFeeModel.
The pessimistic one-tick-slippage FillModel applies to all (§6.4).
"""

from __future__ import annotations

from decimal import Decimal

from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.models import MakerTakerFeeModel
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.model.instruments import (
    CryptoPerpetual,
    CurrencyPair,
    Instrument,
)
from nautilus_trader.model.objects import Money

from backtest.costs import DEFAULT_COST_MODEL, CostModel
from backtest.strategies.sma_cross import SmaCross, SmaCrossConfig


def _venue_config(instrument: Instrument, cost_model: CostModel) -> dict:
    """Account type, currencies, and fee model for the instrument class.

    `base_currency=None` on a CASH venue makes it multi-currency — required by
    nautilus for spot pairs, where the account holds base AND quote balances.
    """
    if isinstance(instrument, CurrencyPair):
        return {
            "account_type": AccountType.CASH,
            "base_currency": None,  # multi-currency account (spot requirement)
            "balance_currency": instrument.quote_currency,
            "fee_model": MakerTakerFeeModel(),  # fees live on the instrument
        }
    if isinstance(instrument, CryptoPerpetual):
        return {
            "account_type": AccountType.MARGIN,
            "base_currency": instrument.settlement_currency,
            "balance_currency": instrument.settlement_currency,
            "fee_model": MakerTakerFeeModel(),
        }
    # Default (FuturesContract today): USD margin + per-contract commission.
    return {
        "account_type": AccountType.MARGIN,
        "base_currency": USD,
        "balance_currency": USD,
        "fee_model": cost_model.fee_model(),
    }


def build_engine(
    instrument: Instrument,
    bars: list[Bar],
    *,
    cost_model: CostModel = DEFAULT_COST_MODEL,
    starting_balance: float = 100_000.0,
    fast_period: int = 10,
    slow_period: int = 30,
    trade_size: str = "1",
    log_level: str = "ERROR",
) -> BacktestEngine:
    """Assemble a ready-to-run engine: venue + instrument + bars + SMA strategy."""
    if not bars:
        raise ValueError("Refusing to build a backtest with zero bars (§6.3).")

    engine = BacktestEngine(
        config=BacktestEngineConfig(
            trader_id=TraderId("BACKTESTER-001"),
            logging=LoggingConfig(log_level=log_level),
        )
    )

    venue_cfg = _venue_config(instrument, cost_model)
    engine.add_venue(
        venue=instrument.id.venue,
        oms_type=OmsType.NETTING,
        account_type=venue_cfg["account_type"],
        starting_balances=[
            Money(Decimal(str(starting_balance)), venue_cfg["balance_currency"])
        ],
        base_currency=venue_cfg["base_currency"],
        fill_model=cost_model.fill_model(),
        fee_model=venue_cfg["fee_model"],
    )

    engine.add_instrument(instrument)
    engine.add_data(bars, sort=True)

    bar_type = bars[0].bar_type
    engine.add_strategy(
        SmaCross(
            SmaCrossConfig(
                instrument_id=instrument.id,
                bar_type=bar_type,
                fast_period=fast_period,
                slow_period=slow_period,
                trade_size=trade_size,
            )
        )
    )
    return engine
