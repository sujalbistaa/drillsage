"""LLM budget ledger, result cache and per-report extraction links (Phase 2b).

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("served_model", sa.String(length=64), nullable=True),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("batch", sa.Boolean(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_creation_input_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_read_input_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Double(), nullable=False),
        sa.Column("stop_reason", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.CheckConstraint("cost_usd >= 0", name=op.f("ck_llm_calls_cost")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_calls")),
    )
    op.create_index(op.f("ix_llm_calls_cache_key"), "llm_calls", ["cache_key"], unique=False)
    op.create_table(
        "llm_results",
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("cache_key", name=op.f("pk_llm_results")),
    )
    op.create_table(
        "llm_extractions",
        sa.Column("report_id", sa.BigInteger(), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("rejected_quotes", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["cache_key"],
            ["llm_results.cache_key"],
            name=op.f("fk_llm_extractions_cache_key_llm_results"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["daily_reports.id"],
            name=op.f("fk_llm_extractions_report_id_daily_reports"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("report_id", "prompt_version", name=op.f("pk_llm_extractions")),
    )


def downgrade() -> None:
    op.drop_table("llm_extractions")
    op.drop_table("llm_results")
    op.drop_index(op.f("ix_llm_calls_cache_key"), table_name="llm_calls")
    op.drop_table("llm_calls")
