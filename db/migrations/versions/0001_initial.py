"""initial schema — §9 seed (instrument, ohlc_bar, option_chain_snapshot,
option_quote, gex_result)

Revision ID: 0001
Revises:
Create Date: 2026-06-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instrument",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("sec_type", sa.String(length=16), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("multiplier", sa.Integer(), nullable=False),
        sa.Column("conid", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint("symbol", "sec_type", name="uq_instrument_symbol_sectype"),
    )
    op.create_index("ix_instrument_symbol", "instrument", ["symbol"])

    op.create_table(
        "ohlc_bar",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instrument.id"), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("open", sa.Numeric(18, 6), nullable=False),
        sa.Column("high", sa.Numeric(18, 6), nullable=False),
        sa.Column("low", sa.Numeric(18, 6), nullable=False),
        sa.Column("close", sa.Numeric(18, 6), nullable=False),
        sa.Column("volume", sa.Numeric(20, 4), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "captured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("instrument_id", "ts", "timeframe", name="uq_ohlc_inst_ts_tf"),
    )
    op.create_index("ix_ohlc_bar_instrument_id", "ohlc_bar", ["instrument_id"])
    op.create_index("ix_ohlc_bar_ts", "ohlc_bar", ["ts"])

    op.create_table(
        "option_chain_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instrument.id"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expiry", sa.String(length=10), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("snapshot_metadata", sa.JSON(), nullable=True),
        sa.UniqueConstraint(
            "instrument_id", "expiry", "captured_at", name="uq_chain_inst_exp_capt"
        ),
    )
    op.create_index("ix_chain_instrument_id", "option_chain_snapshot", ["instrument_id"])
    op.create_index("ix_chain_captured_at", "option_chain_snapshot", ["captured_at"])

    op.create_table(
        "option_quote",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "snapshot_id", sa.Integer(), sa.ForeignKey("option_chain_snapshot.id"), nullable=False
        ),
        sa.Column("strike", sa.Numeric(18, 6), nullable=False),
        sa.Column("right", sa.String(length=1), nullable=False),
        sa.Column("open_interest", sa.Integer(), nullable=True),
        sa.Column("gamma", sa.Numeric(18, 10), nullable=True),
        sa.Column("iv", sa.Numeric(18, 10), nullable=True),
        sa.UniqueConstraint("snapshot_id", "strike", "right", name="uq_quote_snap_strike_right"),
    )
    op.create_index("ix_quote_snapshot_id", "option_quote", ["snapshot_id"])

    op.create_table(
        "gex_result",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "snapshot_id", sa.Integer(), sa.ForeignKey("option_chain_snapshot.id"), nullable=False
        ),
        sa.Column("dealer_sign_convention", sa.String(length=32), nullable=False),
        sa.Column("assumption_dependent", sa.Boolean(), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("call_wall", sa.Numeric(18, 6), nullable=True),
        sa.Column("put_wall", sa.Numeric(18, 6), nullable=True),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("snapshot_id", "dealer_sign_convention", name="uq_gex_snap_convention"),
    )
    op.create_index("ix_gex_snapshot_id", "gex_result", ["snapshot_id"])


def downgrade() -> None:
    op.drop_table("gex_result")
    op.drop_table("option_quote")
    op.drop_table("option_chain_snapshot")
    op.drop_table("ohlc_bar")
    op.drop_table("instrument")
