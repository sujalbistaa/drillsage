"""Canonical well and report model (Phase 1).

Wells, wellbores, daily reports and their sections (activities, fluids, surveys, pore
pressure, lithology, strat picks, gas, casing, equipment failures), file provenance, and the
derived trajectory and formation-top tables. See `drillsage.db.models` for column semantics.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_files",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("parser_version", sa.String(length=32), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_source_files_sha256_hex")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_files")),
        sa.UniqueConstraint("sha256", name=op.f("uq_source_files_sha256")),
    )
    op.create_table(
        "wells",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("field", sa.String(length=64), nullable=True),
        sa.Column("surface_lat_deg", sa.Double(), nullable=False),
        sa.Column("surface_lon_deg", sa.Double(), nullable=False),
        sa.Column("surface_easting_m", sa.Double(), nullable=False),
        sa.Column("surface_northing_m", sa.Double(), nullable=False),
        sa.Column("utm_epsg", sa.Integer(), nullable=False),
        sa.Column("source_datum", sa.String(length=16), nullable=False),
        sa.Column("source_lat_deg", sa.Double(), nullable=False),
        sa.Column("source_lon_deg", sa.Double(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_wells")),
        sa.UniqueConstraint("name", name=op.f("uq_wells_name")),
    )
    op.create_table(
        "wellbores",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("well_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("npdid", sa.Integer(), nullable=True),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=True),
        sa.Column("content", sa.String(length=64), nullable=True),
        sa.Column("operator", sa.String(length=128), nullable=True),
        sa.Column("rig_name", sa.String(length=128), nullable=True),
        sa.Column("kickoff_md_m", sa.Double(), nullable=True),
        sa.Column("kb_elevation_m", sa.Double(), nullable=True),
        sa.Column("water_depth_m", sa.Double(), nullable=True),
        sa.Column("total_depth_md_m", sa.Double(), nullable=True),
        sa.Column("final_tvd_m", sa.Double(), nullable=True),
        sa.Column("spud_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_on", sa.Date(), nullable=True),
        sa.Column("first_report_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_report_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('initial', 'sidetrack', 'technical_sidetrack', 're-entry')",
            name=op.f("ck_wellbores_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["wellbores.id"],
            name=op.f("fk_wellbores_parent_id_wellbores"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["well_id"], ["wells.id"], name=op.f("fk_wellbores_well_id_wells"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_wellbores")),
        sa.UniqueConstraint("name", name=op.f("uq_wellbores_name")),
    )
    op.create_index(op.f("ix_wellbores_npdid"), "wellbores", ["npdid"], unique=False)
    op.create_index(op.f("ix_wellbores_well_id"), "wellbores", ["well_id"], unique=False)
    op.create_table(
        "daily_reports",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("wellbore_id", sa.BigInteger(), nullable=False),
        sa.Column("source_file_id", sa.BigInteger(), nullable=False),
        sa.Column("report_no", sa.Integer(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("md_m", sa.Double(), nullable=True),
        sa.Column("tvd_m", sa.Double(), nullable=True),
        sa.Column("md_planned_m", sa.Double(), nullable=True),
        sa.Column("dist_drill_m", sa.Double(), nullable=True),
        sa.Column("hole_diameter_m", sa.Double(), nullable=True),
        sa.Column("md_hole_diameter_start_m", sa.Double(), nullable=True),
        sa.Column("pilot_diameter_m", sa.Double(), nullable=True),
        sa.Column("md_kickoff_m", sa.Double(), nullable=True),
        sa.Column("md_plug_top_m", sa.Double(), nullable=True),
        sa.Column("strength_form_gcc", sa.Double(), nullable=True),
        sa.Column("md_strength_form_m", sa.Double(), nullable=True),
        sa.Column("tvd_strength_form_m", sa.Double(), nullable=True),
        sa.Column("pres_test_type", sa.String(length=64), nullable=True),
        sa.Column("md_csg_last_m", sa.Double(), nullable=True),
        sa.Column("tvd_csg_last_m", sa.Double(), nullable=True),
        sa.Column("elev_kelly_m", sa.Double(), nullable=True),
        sa.Column("wellhead_elevation_m", sa.Double(), nullable=True),
        sa.Column("water_depth_m", sa.Double(), nullable=True),
        sa.Column("rop_current_mph", sa.Double(), nullable=True),
        sa.Column("avg_pres_bh_kpa", sa.Double(), nullable=True),
        sa.Column("avg_temp_bh_degc", sa.Double(), nullable=True),
        sa.Column("tight_well", sa.Boolean(), nullable=True),
        sa.Column("hpht", sa.Boolean(), nullable=True),
        sa.Column("fixed_rig", sa.Boolean(), nullable=True),
        sa.Column("summary_24h", sa.Text(), nullable=True),
        sa.Column("forecast_24h", sa.Text(), nullable=True),
        sa.Column("operator", sa.String(length=128), nullable=True),
        sa.Column("drill_contractor", sa.String(length=128), nullable=True),
        sa.Column("rig_name", sa.String(length=128), nullable=True),
        sa.Column("days_ahead", sa.Double(), nullable=True),
        sa.Column("days_behind", sa.Double(), nullable=True),
        sa.Column(
            "extra",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint("end_at > start_at", name=op.f("ck_daily_reports_period")),
        sa.ForeignKeyConstraint(
            ["source_file_id"],
            ["source_files.id"],
            name=op.f("fk_daily_reports_source_file_id_source_files"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["wellbore_id"],
            ["wellbores.id"],
            name=op.f("fk_daily_reports_wellbore_id_wellbores"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_daily_reports")),
        sa.UniqueConstraint(
            "wellbore_id", "start_at", name=op.f("uq_daily_reports_wellbore_id_start_at")
        ),
    )
    op.create_index(
        op.f("ix_daily_reports_source_file_id"), "daily_reports", ["source_file_id"], unique=False
    )
    op.create_table(
        "formation_tops",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("wellbore_id", sa.BigInteger(), nullable=False),
        sa.Column("basin_pack", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("md_top_m", sa.Double(), nullable=False),
        sa.Column("tvd_top_m", sa.Double(), nullable=True),
        sa.Column("tvdss_top_m", sa.Double(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("raw_name", sa.String(length=128), nullable=False),
        sa.Column("inherited_from_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["inherited_from_id"],
            ["wellbores.id"],
            name=op.f("fk_formation_tops_inherited_from_id_wellbores"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["wellbore_id"],
            ["wellbores.id"],
            name=op.f("fk_formation_tops_wellbore_id_wellbores"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_formation_tops")),
        sa.UniqueConstraint(
            "wellbore_id", "name", "level", name=op.f("uq_formation_tops_wellbore_id_name_level")
        ),
    )
    op.create_index("ix_formation_tops_name", "formation_tops", ["name"], unique=False)
    op.create_table(
        "trajectory_stations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("wellbore_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("md_m", sa.Double(), nullable=False),
        sa.Column("tvd_m", sa.Double(), nullable=False),
        sa.Column("tvdss_m", sa.Double(), nullable=True),
        sa.Column("incl_deg", sa.Double(), nullable=False),
        sa.Column("azi_deg", sa.Double(), nullable=False),
        sa.Column("north_m", sa.Double(), nullable=False),
        sa.Column("east_m", sa.Double(), nullable=False),
        sa.Column("easting_m", sa.Double(), nullable=False),
        sa.Column("northing_m", sa.Double(), nullable=False),
        sa.Column("dls_deg_per_30m", sa.Double(), nullable=False),
        sa.Column("tvd_mincurv_m", sa.Double(), nullable=False),
        sa.Column("tvd_reported_m", sa.Double(), nullable=True),
        sa.Column("tvd_source", sa.String(length=16), nullable=False),
        sa.Column("reported_tvd_rejected", sa.Boolean(), nullable=False),
        sa.Column("inherited", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["wellbore_id"],
            ["wellbores.id"],
            name=op.f("fk_trajectory_stations_wellbore_id_wellbores"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trajectory_stations")),
        sa.UniqueConstraint(
            "wellbore_id", "md_m", name=op.f("uq_trajectory_stations_wellbore_id_md_m")
        ),
        sa.UniqueConstraint(
            "wellbore_id", "seq", name=op.f("uq_trajectory_stations_wellbore_id_seq")
        ),
    )
    op.create_table(
        "activities",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("report_id", sa.BigInteger(), nullable=False),
        sa.Column("wellbore_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_h", sa.Double(), nullable=True),
        sa.Column("md_m", sa.Double(), nullable=True),
        sa.Column("phase", sa.String(length=32), nullable=True),
        sa.Column("proprietary_code", sa.String(length=128), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=True),
        sa.Column("state_detail", sa.String(length=64), nullable=True),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["daily_reports.id"],
            name=op.f("fk_activities_report_id_daily_reports"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["wellbore_id"],
            ["wellbores.id"],
            name=op.f("fk_activities_wellbore_id_wellbores"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_activities")),
        sa.UniqueConstraint("report_id", "seq", name=op.f("uq_activities_report_id_seq")),
    )
    op.create_index("ix_activities_code", "activities", ["proprietary_code"], unique=False)
    op.create_index(op.f("ix_activities_report_id"), "activities", ["report_id"], unique=False)
    op.create_index("ix_activities_state_detail", "activities", ["state_detail"], unique=False)
    op.create_index(
        "ix_activities_wellbore_start", "activities", ["wellbore_id", "start_at"], unique=False
    )
    op.create_table(
        "casing_strings",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("report_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
        sa.Column("string_type", sa.String(length=8), nullable=True),
        sa.Column("outer_diameter_m", sa.Double(), nullable=True),
        sa.Column("inner_diameter_m", sa.Double(), nullable=True),
        sa.Column("weight_kgpm", sa.Double(), nullable=True),
        sa.Column("grade", sa.String(length=32), nullable=True),
        sa.Column("connection", sa.String(length=64), nullable=True),
        sa.Column("length_m", sa.Double(), nullable=True),
        sa.Column("md_top_m", sa.Double(), nullable=True),
        sa.Column("md_bottom_m", sa.Double(), nullable=True),
        sa.Column("casing_type", sa.String(length=64), nullable=True),
        sa.Column("run_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["daily_reports.id"],
            name=op.f("fk_casing_strings_report_id_daily_reports"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_casing_strings")),
        sa.UniqueConstraint("report_id", "seq", name=op.f("uq_casing_strings_report_id_seq")),
    )
    op.create_index(
        op.f("ix_casing_strings_report_id"), "casing_strings", ["report_id"], unique=False
    )
    op.create_table(
        "equipment_failures",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("report_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("md_m", sa.Double(), nullable=True),
        sa.Column("equip_class", sa.String(length=128), nullable=True),
        sa.Column("missed_production_h", sa.Double(), nullable=True),
        sa.Column("repaired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["daily_reports.id"],
            name=op.f("fk_equipment_failures_report_id_daily_reports"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_equipment_failures")),
        sa.UniqueConstraint("report_id", "seq", name=op.f("uq_equipment_failures_report_id_seq")),
    )
    op.create_index(
        op.f("ix_equipment_failures_report_id"), "equipment_failures", ["report_id"], unique=False
    )
    op.create_table(
        "fluids",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("report_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("md_m", sa.Double(), nullable=True),
        sa.Column("fluid_type", sa.String(length=64), nullable=True),
        sa.Column("mud_class", sa.String(length=32), nullable=True),
        sa.Column("location_sample", sa.String(length=64), nullable=True),
        sa.Column("density_gcc", sa.Double(), nullable=True),
        sa.Column("vis_funnel_s", sa.Double(), nullable=True),
        sa.Column("pv_mpas", sa.Double(), nullable=True),
        sa.Column("yp_pa", sa.Double(), nullable=True),
        sa.Column("pres_bop_rating_kpa", sa.Double(), nullable=True),
        sa.Column("temp_hthp_degc", sa.Double(), nullable=True),
        sa.Column("filtrate_ltlp_m3", sa.Double(), nullable=True),
        sa.Column("filter_cake_ltlp_m", sa.Double(), nullable=True),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["daily_reports.id"],
            name=op.f("fk_fluids_report_id_daily_reports"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fluids")),
        sa.UniqueConstraint("report_id", "seq", name=op.f("uq_fluids_report_id_seq")),
    )
    op.create_index(op.f("ix_fluids_report_id"), "fluids", ["report_id"], unique=False)
    op.create_table(
        "gas_readings",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("report_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reading_type", sa.String(length=32), nullable=True),
        sa.Column("md_top_m", sa.Double(), nullable=True),
        sa.Column("tvd_top_m", sa.Double(), nullable=True),
        sa.Column("gas_high_pct", sa.Double(), nullable=True),
        sa.Column("methane_ppm", sa.Double(), nullable=True),
        sa.Column("ethane_ppm", sa.Double(), nullable=True),
        sa.Column("propane_ppm", sa.Double(), nullable=True),
        sa.Column("ibutane_ppm", sa.Double(), nullable=True),
        sa.Column("nbutane_ppm", sa.Double(), nullable=True),
        sa.Column("ipentane_ppm", sa.Double(), nullable=True),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["daily_reports.id"],
            name=op.f("fk_gas_readings_report_id_daily_reports"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gas_readings")),
        sa.UniqueConstraint("report_id", "seq", name=op.f("uq_gas_readings_report_id_seq")),
    )
    op.create_index(op.f("ix_gas_readings_report_id"), "gas_readings", ["report_id"], unique=False)
    op.create_table(
        "lithology_shows",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("report_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("md_top_m", sa.Double(), nullable=True),
        sa.Column("md_bottom_m", sa.Double(), nullable=True),
        sa.Column("tvd_top_m", sa.Double(), nullable=True),
        sa.Column("tvd_bottom_m", sa.Double(), nullable=True),
        sa.Column("lithology", sa.Text(), nullable=True),
        sa.Column("show", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["daily_reports.id"],
            name=op.f("fk_lithology_shows_report_id_daily_reports"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lithology_shows")),
        sa.UniqueConstraint("report_id", "seq", name=op.f("uq_lithology_shows_report_id_seq")),
    )
    op.create_index(
        op.f("ix_lithology_shows_report_id"), "lithology_shows", ["report_id"], unique=False
    )
    op.create_table(
        "pore_pressures",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("report_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("md_m", sa.Double(), nullable=True),
        sa.Column("emw_gcc", sa.Double(), nullable=True),
        sa.Column("reading_kind", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["daily_reports.id"],
            name=op.f("fk_pore_pressures_report_id_daily_reports"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pore_pressures")),
        sa.UniqueConstraint("report_id", "seq", name=op.f("uq_pore_pressures_report_id_seq")),
    )
    op.create_index(
        op.f("ix_pore_pressures_report_id"), "pore_pressures", ["report_id"], unique=False
    )
    op.create_table(
        "strat_picks",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("report_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("md_top_m", sa.Double(), nullable=True),
        sa.Column("tvd_top_m", sa.Double(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["daily_reports.id"],
            name=op.f("fk_strat_picks_report_id_daily_reports"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strat_picks")),
        sa.UniqueConstraint("report_id", "seq", name=op.f("uq_strat_picks_report_id_seq")),
    )
    op.create_index(op.f("ix_strat_picks_report_id"), "strat_picks", ["report_id"], unique=False)
    op.create_table(
        "survey_stations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("report_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("md_m", sa.Double(), nullable=True),
        sa.Column("tvd_m", sa.Double(), nullable=True),
        sa.Column("incl_deg", sa.Double(), nullable=True),
        sa.Column("azi_deg", sa.Double(), nullable=True),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["daily_reports.id"],
            name=op.f("fk_survey_stations_report_id_daily_reports"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_survey_stations")),
        sa.UniqueConstraint("report_id", "seq", name=op.f("uq_survey_stations_report_id_seq")),
    )
    op.create_index(
        op.f("ix_survey_stations_report_id"), "survey_stations", ["report_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_survey_stations_report_id"), table_name="survey_stations")
    op.drop_table("survey_stations")
    op.drop_index(op.f("ix_strat_picks_report_id"), table_name="strat_picks")
    op.drop_table("strat_picks")
    op.drop_index(op.f("ix_pore_pressures_report_id"), table_name="pore_pressures")
    op.drop_table("pore_pressures")
    op.drop_index(op.f("ix_lithology_shows_report_id"), table_name="lithology_shows")
    op.drop_table("lithology_shows")
    op.drop_index(op.f("ix_gas_readings_report_id"), table_name="gas_readings")
    op.drop_table("gas_readings")
    op.drop_index(op.f("ix_fluids_report_id"), table_name="fluids")
    op.drop_table("fluids")
    op.drop_index(op.f("ix_equipment_failures_report_id"), table_name="equipment_failures")
    op.drop_table("equipment_failures")
    op.drop_index(op.f("ix_casing_strings_report_id"), table_name="casing_strings")
    op.drop_table("casing_strings")
    op.drop_index("ix_activities_wellbore_start", table_name="activities")
    op.drop_index("ix_activities_state_detail", table_name="activities")
    op.drop_index(op.f("ix_activities_report_id"), table_name="activities")
    op.drop_index("ix_activities_code", table_name="activities")
    op.drop_table("activities")
    op.drop_table("trajectory_stations")
    op.drop_index("ix_formation_tops_name", table_name="formation_tops")
    op.drop_table("formation_tops")
    op.drop_index(op.f("ix_daily_reports_source_file_id"), table_name="daily_reports")
    op.drop_table("daily_reports")
    op.drop_index(op.f("ix_wellbores_well_id"), table_name="wellbores")
    op.drop_index(op.f("ix_wellbores_npdid"), table_name="wellbores")
    op.drop_table("wellbores")
    op.drop_table("wells")
    op.drop_table("source_files")
