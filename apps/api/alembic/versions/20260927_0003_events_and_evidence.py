"""Events and evidence (Phase 2).

`events` holds extracted drilling-problem episodes per extractor tier; `event_evidence` links
each event to the activities and exact character spans it was derived from.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("wellbore_id", sa.BigInteger(), nullable=False),
        sa.Column("hazard", sa.String(length=32), nullable=False),
        sa.Column("subtype", sa.String(length=64), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("md_top_m", sa.Double(), nullable=True),
        sa.Column("md_bottom_m", sa.Double(), nullable=True),
        sa.Column("depth_source", sa.String(length=16), nullable=False),
        sa.Column("tvd_top_m", sa.Double(), nullable=True),
        sa.Column("tvd_bottom_m", sa.Double(), nullable=True),
        sa.Column("tvdss_top_m", sa.Double(), nullable=True),
        sa.Column("tvdss_bottom_m", sa.Double(), nullable=True),
        sa.Column("formation", sa.String(length=64), nullable=True),
        sa.Column("formation_group", sa.String(length=64), nullable=True),
        sa.Column("formation_source", sa.String(length=16), nullable=True),
        sa.Column("hole_diameter_m", sa.Double(), nullable=True),
        sa.Column("mud_density_gcc", sa.Double(), nullable=True),
        sa.Column("mud_class", sa.String(length=32), nullable=True),
        sa.Column("severity", sa.SmallInteger(), nullable=False),
        sa.Column("npt_h", sa.Double(), nullable=False),
        sa.Column("led_to_sidetrack", sa.Boolean(), nullable=False),
        sa.Column("detected_by", sa.String(length=16), nullable=False),
        sa.Column("confidence_tier", sa.String(length=16), nullable=False),
        sa.Column("extractor_version", sa.String(length=32), nullable=False),
        sa.Column("n_activities", sa.Integer(), nullable=False),
        sa.Column(
            "mitigations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence_tier IN ('rule', 'llm', 'rule+llm', 'human')",
            name=op.f("ck_events_confidence_tier"),
        ),
        sa.CheckConstraint("npt_h >= 0", name=op.f("ck_events_npt")),
        sa.CheckConstraint("severity BETWEEN 1 AND 4", name=op.f("ck_events_severity")),
        sa.ForeignKeyConstraint(
            ["wellbore_id"],
            ["wellbores.id"],
            name=op.f("fk_events_wellbore_id_wellbores"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
    )
    op.create_index("ix_events_formation", "events", ["formation"], unique=False)
    op.create_index("ix_events_tier", "events", ["confidence_tier"], unique=False)
    op.create_index("ix_events_wellbore_hazard", "events", ["wellbore_id", "hazard"], unique=False)
    op.create_table(
        "event_evidence",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("activity_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "(char_start IS NULL AND char_end IS NULL)"
            " OR (char_start >= 0 AND char_end > char_start)",
            name=op.f("ck_event_evidence_span"),
        ),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["activities.id"],
            name=op.f("fk_event_evidence_activity_id_activities"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_event_evidence_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_evidence")),
    )
    op.create_index(
        op.f("ix_event_evidence_activity_id"), "event_evidence", ["activity_id"], unique=False
    )
    op.create_index(
        op.f("ix_event_evidence_event_id"), "event_evidence", ["event_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_event_evidence_event_id"), table_name="event_evidence")
    op.drop_index(op.f("ix_event_evidence_activity_id"), table_name="event_evidence")
    op.drop_table("event_evidence")
    op.drop_index("ix_events_wellbore_hazard", table_name="events")
    op.drop_index("ix_events_tier", table_name="events")
    op.drop_index("ix_events_formation", table_name="events")
    op.drop_table("events")
