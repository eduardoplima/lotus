"""crypto price precision bump + funding_rate table (§6.3, §6.4)

ohlc_bar o/h/l/c Numeric(18,6) -> (30,12) and volume (20,4) -> (30,10): six
decimals cannot represent low-priced crypto pairs (PEPE ~1e-6). funding_rate
records perp funding accruals with full provenance — a perp backtest without
funding is not costed.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for col in ("open", "high", "low", "close"):
        op.alter_column(
            "ohlc_bar", col, type_=sa.Numeric(30, 12), existing_type=sa.Numeric(18, 6)
        )
    op.alter_column(
        "ohlc_bar", "volume", type_=sa.Numeric(30, 10), existing_type=sa.Numeric(20, 4)
    )

    op.create_table(
        "funding_rate",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instrument.id"), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rate", sa.Numeric(20, 12), nullable=False),
        sa.Column("premium", sa.Numeric(20, 12), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "captured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("vintage", sa.String(length=32), nullable=False),
        sa.UniqueConstraint("instrument_id", "ts", name="uq_funding_inst_ts"),
    )
    op.create_index("ix_funding_rate_instrument_id", "funding_rate", ["instrument_id"])
    op.create_index("ix_funding_rate_ts", "funding_rate", ["ts"])


def downgrade() -> None:
    op.drop_table("funding_rate")
    for col in ("open", "high", "low", "close"):
        op.alter_column(
            "ohlc_bar", col, type_=sa.Numeric(18, 6), existing_type=sa.Numeric(30, 12)
        )
    op.alter_column(
        "ohlc_bar", "volume", type_=sa.Numeric(20, 4), existing_type=sa.Numeric(30, 10)
    )
