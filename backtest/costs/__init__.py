"""Pessimistic cost model (§6.4).

A strategy result without realistic costs is meaningless. When a cost is
uncertain, we default to the pessimistic estimate. For MES the dominant costs
are per-contract commission/exchange fees and one-tick slippage on entry/exit.

These are deliberately worse than a good retail fill:
  * MES all-in commission ≈ $0.52 (IB) + exchange/regulatory ≈ $0.35 → ~$0.87.
    We charge **$1.00 per contract** to stay pessimistic.
  * We assume orders **always slip one tick** ($1.25 on MES) against us.

Values are configurable; the point is that the default punishes, never flatters.
"""

from __future__ import annotations

from dataclasses import dataclass

from nautilus_trader.backtest.models import FillModel, PerContractFeeModel
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.objects import Money


@dataclass(frozen=True)
class CostModel:
    """Pessimistic cost assumptions for a futures venue."""

    commission_per_contract: float = 1.00  # USD, pessimistic vs ~$0.87 realistic
    prob_slippage: float = 1.0  # always slip one tick against us
    prob_fill_on_limit: float = 1.0  # resting limit fills when market touches
    random_seed: int = 7  # fixed → deterministic, reproducible runs

    def to_dict(self) -> dict[str, float | str]:
        return {
            "commission_per_contract_usd": self.commission_per_contract,
            "prob_slippage": self.prob_slippage,
            "prob_fill_on_limit": self.prob_fill_on_limit,
            "slippage_model": "one_tick_against",
        }

    def fill_model(self) -> FillModel:
        return FillModel(
            prob_fill_on_limit=self.prob_fill_on_limit,
            prob_slippage=self.prob_slippage,
            random_seed=self.random_seed,
        )

    def fee_model(self) -> PerContractFeeModel:
        return PerContractFeeModel(Money(self.commission_per_contract, USD))


DEFAULT_COST_MODEL = CostModel()
