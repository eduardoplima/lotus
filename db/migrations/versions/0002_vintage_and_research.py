"""vintage columns (§6.3) + research schema — hypothesis, backtest_run,
backtest_result (§9)

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- vintage (§6.3): never null. Add with a transient server_default so the
    # migration is safe on any pre-existing rows, then drop the default so the
    # application must always supply a vintage explicitly. ---
    for table in ("ohlc_bar", "option_chain_snapshot"):
        op.add_column(
            table,
            sa.Column("vintage", sa.String(length=32), nullable=False, server_default="unknown"),
        )
        op.alter_column(table, "vintage", server_default=None)

    # --- Research schema (§9) ---
    op.create_table(
        "hypothesis",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("baseline", sa.Text(), nullable=False),
        sa.Column("signal_threshold", sa.Text(), nullable=False),
        sa.Column("dev_split_def", sa.Text(), nullable=False),
        sa.Column("kill_test", sa.Text(), nullable=False),
        sa.Column("kill_criteria", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("killed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("kill_reason", sa.Text(), nullable=True),
        sa.UniqueConstraint("statement", name="uq_hypothesis_statement"),
    )

    op.create_table(
        "backtest_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hypothesis_id", sa.Integer(), sa.ForeignKey("hypothesis.id"), nullable=True),
        sa.Column("strategy", sa.String(length=64), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("data_window", sa.JSON(), nullable=False),
        sa.Column("cost_model", sa.JSON(), nullable=False),
        sa.Column("code_version", sa.String(length=64), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("config_hash", name="uq_run_config_hash"),
    )
    op.create_index("ix_run_hypothesis_id", "backtest_run", ["hypothesis_id"])
    op.create_index("ix_run_config_hash", "backtest_run", ["config_hash"])

    op.create_table(
        "backtest_result",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("backtest_run.id"), nullable=False),
        sa.Column("headline", sa.JSON(), nullable=False),
        sa.Column("stress_windows", sa.JSON(), nullable=False),
        sa.Column("tail", sa.JSON(), nullable=False),
        sa.Column("equity_curve_ref", sa.String(length=256), nullable=True),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("run_id", name="uq_result_run"),
    )
    op.create_index("ix_result_run_id", "backtest_result", ["run_id"])


def downgrade() -> None:
    op.drop_table("backtest_result")
    op.drop_table("backtest_run")
    op.drop_table("hypothesis")
    for table in ("option_chain_snapshot", "ohlc_bar"):
        op.drop_column(table, "vintage")
