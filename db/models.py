"""SQLAlchemy ORM models — the §9 seed schema.

Refine via Alembic migrations; this is the starting shape, not the final one.

Integrity invariants baked into the schema (§6.2/§6.3):
  * `captured_at` is never null — every datum records when it was captured.
  * Snapshots and quotes carry unique keys to prevent duplicate captures and
    are written once; nothing here mutates them on update.
  * GEX results always trace back to the immutable chain snapshot they came
    from, and record the dealer-sign convention they assumed.

Only `instrument` and `ohlc_bar` are exercised at M0. The option-chain and GEX
tables are present as the documented seed for M1/M2.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class HypothesisStatus(StrEnum):
    """Lifecycle of a pre-registered hypothesis (§7.1/§7.2).

    `killed` rows are never deleted — they are the failure cemetery (§7.2), part
    of the multiple-testing denominator.
    """

    REGISTERED = "registered"
    LIVE = "live"
    KILLED = "killed"


class Instrument(Base):
    __tablename__ = "instrument"
    __table_args__ = (UniqueConstraint("symbol", "sec_type", name="uq_instrument_symbol_sectype"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    sec_type: Mapped[str] = mapped_column(String(16), default="STK")
    exchange: Mapped[str] = mapped_column(String(32), default="SMART")
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    multiplier: Mapped[int] = mapped_column(default=1)
    conid: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    bars: Mapped[list[OhlcBar]] = relationship(back_populates="instrument")


class OhlcBar(Base):
    __tablename__ = "ohlc_bar"
    __table_args__ = (
        UniqueConstraint("instrument_id", "ts", "timeframe", name="uq_ohlc_inst_ts_tf"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instrument.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    timeframe: Mapped[str] = mapped_column(String(8))  # e.g. "1d"
    # Numeric(30,12): wide enough for BTC-scale integers AND sub-cent crypto
    # (PEPE ~1e-6 with tick sizes down to 1e-10). Bumped from (18,6) in 0003.
    open: Mapped[float] = mapped_column(Numeric(30, 12))
    high: Mapped[float] = mapped_column(Numeric(30, 12))
    low: Mapped[float] = mapped_column(Numeric(30, 12))
    close: Mapped[float] = mapped_column(Numeric(30, 12))
    volume: Mapped[float | None] = mapped_column(Numeric(30, 10), nullable=True)
    # Provenance (§6.3): where this came from, when we captured it, and the
    # as-of vintage under which the datum was known. `vintage` never null —
    # backtests query as-of a vintage to stay point-in-time correct (§6.1).
    source: Mapped[str] = mapped_column(String(32), default="IBKR")
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    vintage: Mapped[str] = mapped_column(String(32))

    instrument: Mapped[Instrument] = relationship(back_populates="bars")


class OptionChainSnapshot(Base):
    """Immutable once written (§6.2) — one capture of a chain for one expiry."""

    __tablename__ = "option_chain_snapshot"
    __table_args__ = (
        UniqueConstraint("instrument_id", "expiry", "captured_at", name="uq_chain_inst_exp_capt"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instrument.id"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expiry: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    source: Mapped[str] = mapped_column(String(32), default="IBKR")
    vintage: Mapped[str] = mapped_column(String(32))  # as-of vintage, never null (§6.3)
    snapshot_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    quotes: Mapped[list[OptionQuote]] = relationship(back_populates="snapshot")
    gex_results: Mapped[list[GexResult]] = relationship(back_populates="snapshot")


class OptionQuote(Base):
    """One contract row within a snapshot. Right is 'C' or 'P'."""

    __tablename__ = "option_quote"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "strike", "right", name="uq_quote_snap_strike_right"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("option_chain_snapshot.id"), index=True)
    strike: Mapped[float] = mapped_column(Numeric(18, 6))
    right: Mapped[str] = mapped_column(String(1))  # 'C' | 'P'
    open_interest: Mapped[int | None] = mapped_column(nullable=True)
    gamma: Mapped[float | None] = mapped_column(Numeric(18, 10), nullable=True)
    iv: Mapped[float | None] = mapped_column(Numeric(18, 10), nullable=True)

    snapshot: Mapped[OptionChainSnapshot] = relationship(back_populates="quotes")


class GexResult(Base):
    """Computed GEX profile + walls, always traceable to its source snapshot.

    `assumption_dependent` is stored true and `dealer_sign_convention` records
    the assumption used — these numbers are modeled, not measured (§6.1).
    """

    __tablename__ = "gex_result"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "dealer_sign_convention", name="uq_gex_snap_convention"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("option_chain_snapshot.id"), index=True)
    dealer_sign_convention: Mapped[str] = mapped_column(String(32))
    assumption_dependent: Mapped[bool] = mapped_column(default=True)
    profile: Mapped[dict] = mapped_column(JSON)  # per-strike gamma exposure
    call_wall: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    put_wall: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    snapshot: Mapped[OptionChainSnapshot] = relationship(back_populates="gex_results")


class FundingRate(Base):
    """One perp funding accrual (Hyperliquid: hourly), with full provenance.

    Funding is part of a perp position's P&L; a perp backtest without funding
    history is not costed (§6.4). Insert-only, unique per (instrument, ts).
    """

    __tablename__ = "funding_rate"
    __table_args__ = (UniqueConstraint("instrument_id", "ts", name="uq_funding_inst_ts"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instrument.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    rate: Mapped[float] = mapped_column(Numeric(20, 12))  # per-accrual rate, e.g. 1.25e-5
    premium: Mapped[float | None] = mapped_column(Numeric(20, 12), nullable=True)
    # Provenance (§6.3).
    source: Mapped[str] = mapped_column(String(32))
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    vintage: Mapped[str] = mapped_column(String(32))


# --------------------------------------------------------------------------- #
# Research schema (§9) — the pre-registration registry, the failure cemetery,  #
# and reproducible run/result provenance.                                      #
# --------------------------------------------------------------------------- #


class Hypothesis(Base):
    """A pre-registered strategy hypothesis (§7.1).

    A hypothesis is not valid until all four fields are recorded *before*
    touching test data: a comparative claim against an unconditional baseline,
    a signal threshold frozen on the dev split, a kill test aimed at the weakest
    assumption, and explicit numeric kill criteria. `status == killed` rows are
    the failure cemetery (§7.2) — never deleted.
    """

    __tablename__ = "hypothesis"
    __table_args__ = (UniqueConstraint("statement", name="uq_hypothesis_statement"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    statement: Mapped[str] = mapped_column(Text)
    baseline: Mapped[str] = mapped_column(Text)  # the dumb unconditional benchmark
    signal_threshold: Mapped[str] = mapped_column(Text)  # frozen ex-ante on dev split
    dev_split_def: Mapped[str] = mapped_column(Text)  # how dev/test is split
    kill_test: Mapped[str] = mapped_column(Text)  # the single most falsifying test
    kill_criteria: Mapped[str] = mapped_column(Text)  # numeric death conditions
    status: Mapped[str] = mapped_column(String(16), default=HypothesisStatus.REGISTERED)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    killed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    kill_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    runs: Mapped[list[BacktestRun]] = relationship(back_populates="hypothesis")


class BacktestRun(Base):
    """One backtest execution, fully reproducible (§6.3/§9).

    Records the exact data window, cost model, and code version (git SHA). A
    `config_hash` (deterministic over strategy+params+data_window+cost_model+
    code_version) is unique so an identical run is not double-counted.
    `hypothesis_id` is nullable for replication/baseline/plumbing runs (§7.3).
    """

    __tablename__ = "backtest_run"
    __table_args__ = (UniqueConstraint("config_hash", name="uq_run_config_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    hypothesis_id: Mapped[int | None] = mapped_column(
        ForeignKey("hypothesis.id"), nullable=True, index=True
    )
    strategy: Mapped[str] = mapped_column(String(64))
    params: Mapped[dict] = mapped_column(JSON)
    data_window: Mapped[dict] = mapped_column(JSON)  # {symbol, start, end, source, vintage}
    cost_model: Mapped[dict] = mapped_column(JSON)  # commissions/slippage/fill assumptions
    code_version: Mapped[str] = mapped_column(String(64))  # git SHA
    config_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    hypothesis: Mapped[Hypothesis | None] = relationship(back_populates="runs")
    result: Mapped[BacktestResult | None] = relationship(back_populates="run", uselist=False)


class BacktestResult(Base):
    """Metrics for a run — headline, per-stress-window, and tail (§7.4/§7.5).

    Tail metrics (max drawdown, worst-window loss) are first-class, never hidden
    behind averages; for short-convexity strategies the tail is the whole story.
    """

    __tablename__ = "backtest_result"
    __table_args__ = (UniqueConstraint("run_id", name="uq_result_run"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("backtest_run.id"), index=True)
    headline: Mapped[dict] = mapped_column(JSON)  # total return, sharpe, n_trades, ...
    stress_windows: Mapped[dict] = mapped_column(JSON)  # per §7.4 window -> metrics
    tail: Mapped[dict] = mapped_column(JSON)  # max_drawdown, worst_window, ...
    equity_curve_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    run: Mapped[BacktestRun] = relationship(back_populates="result")
