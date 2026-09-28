"""Canonical relational model (Phase 1).

Conventions:
- Every quantity is stored in its canonical unit (see `drillsage.core.units`); the unit is in
  the column name.
- Depths are MD or TVD from the rig's kelly bushing (RKB) unless the name says `tvdss`
  (true vertical depth below mean sea level), which is what cross-well comparisons use.
- Rows parsed from a file point to their `source_files` row (provenance). Child rows keep
  their position in the source report (`seq`) so evidence can cite "activity 7 of report X".
- Derived tables (`trajectory_stations`, `formation_tops`) are rebuilt deterministically.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Double,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from drillsage.db.base import Base


def _pk() -> Mapped[int]:
    return mapped_column(BigInteger, Identity(always=True), primary_key=True)


def _report_fk() -> Mapped[int]:
    return mapped_column(ForeignKey("daily_reports.id", ondelete="CASCADE"), index=True)


class SourceFile(Base):
    __tablename__ = "source_files"

    id: Mapped[int] = _pk()
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(32))
    """`ddr_xml`, `sodir_wellbores_csv`, `sodir_litho_csv`."""
    source: Mapped[str] = mapped_column(String(128))
    path: Mapped[str] = mapped_column(Text)
    """Path relative to the data directory."""
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    parser_version: Mapped[str] = mapped_column(String(32))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_hex"),)


class Well(Base):
    __tablename__ = "wells"

    id: Mapped[int] = _pk()
    name: Mapped[str] = mapped_column(String(64), unique=True)
    field: Mapped[str | None] = mapped_column(String(64))
    surface_lat_deg: Mapped[float] = mapped_column(Double)
    surface_lon_deg: Mapped[float] = mapped_column(Double)
    """WGS84."""
    surface_easting_m: Mapped[float] = mapped_column(Double)
    surface_northing_m: Mapped[float] = mapped_column(Double)
    utm_epsg: Mapped[int] = mapped_column(Integer)
    source_datum: Mapped[str] = mapped_column(String(16))
    source_lat_deg: Mapped[float] = mapped_column(Double)
    source_lon_deg: Mapped[float] = mapped_column(Double)


class Wellbore(Base):
    __tablename__ = "wellbores"

    id: Mapped[int] = _pk()
    well_id: Mapped[int] = mapped_column(ForeignKey("wells.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    npdid: Mapped[int | None] = mapped_column(Integer, index=True)
    """Regulator id; technical sidetracks share their parent's id."""
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("wellbores.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(24))
    """`initial`, `sidetrack`, `technical_sidetrack` or `re-entry`."""
    purpose: Mapped[str | None] = mapped_column(String(32))
    content: Mapped[str | None] = mapped_column(String(64))
    operator: Mapped[str | None] = mapped_column(String(128))
    rig_name: Mapped[str | None] = mapped_column(String(128))
    kickoff_md_m: Mapped[float | None] = mapped_column(Double)
    kb_elevation_m: Mapped[float | None] = mapped_column(Double)
    water_depth_m: Mapped[float | None] = mapped_column(Double)
    total_depth_md_m: Mapped[float | None] = mapped_column(Double)
    final_tvd_m: Mapped[float | None] = mapped_column(Double)
    spud_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_on: Mapped[date | None] = mapped_column(Date)
    """Temporal backtests use only offset wells completed before a well's spud."""
    first_report_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_report_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "kind IN ('initial', 'sidetrack', 'technical_sidetrack', 're-entry')", name="kind"
        ),
    )


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id: Mapped[int] = _pk()
    wellbore_id: Mapped[int] = mapped_column(ForeignKey("wellbores.id", ondelete="CASCADE"))
    source_file_id: Mapped[int] = mapped_column(
        ForeignKey("source_files.id", ondelete="CASCADE"), index=True
    )
    report_no: Mapped[int | None] = mapped_column(Integer)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    md_m: Mapped[float | None] = mapped_column(Double)
    tvd_m: Mapped[float | None] = mapped_column(Double)
    md_planned_m: Mapped[float | None] = mapped_column(Double)
    dist_drill_m: Mapped[float | None] = mapped_column(Double)
    hole_diameter_m: Mapped[float | None] = mapped_column(Double)
    md_hole_diameter_start_m: Mapped[float | None] = mapped_column(Double)
    pilot_diameter_m: Mapped[float | None] = mapped_column(Double)
    md_kickoff_m: Mapped[float | None] = mapped_column(Double)
    md_plug_top_m: Mapped[float | None] = mapped_column(Double)
    strength_form_gcc: Mapped[float | None] = mapped_column(Double)
    """Formation strength (LOT/FIT) as equivalent mud density."""
    md_strength_form_m: Mapped[float | None] = mapped_column(Double)
    tvd_strength_form_m: Mapped[float | None] = mapped_column(Double)
    pres_test_type: Mapped[str | None] = mapped_column(String(64))
    md_csg_last_m: Mapped[float | None] = mapped_column(Double)
    tvd_csg_last_m: Mapped[float | None] = mapped_column(Double)
    elev_kelly_m: Mapped[float | None] = mapped_column(Double)
    wellhead_elevation_m: Mapped[float | None] = mapped_column(Double)
    water_depth_m: Mapped[float | None] = mapped_column(Double)
    rop_current_mph: Mapped[float | None] = mapped_column(Double)
    avg_pres_bh_kpa: Mapped[float | None] = mapped_column(Double)
    avg_temp_bh_degc: Mapped[float | None] = mapped_column(Double)
    tight_well: Mapped[bool | None] = mapped_column(Boolean)
    hpht: Mapped[bool | None] = mapped_column(Boolean)
    fixed_rig: Mapped[bool | None] = mapped_column(Boolean)
    summary_24h: Mapped[str | None] = mapped_column(Text)
    forecast_24h: Mapped[str | None] = mapped_column(Text)
    operator: Mapped[str | None] = mapped_column(String(128))
    drill_contractor: Mapped[str | None] = mapped_column(String(128))
    rig_name: Mapped[str | None] = mapped_column(String(128))
    days_ahead: Mapped[float | None] = mapped_column(Double)
    days_behind: Mapped[float | None] = mapped_column(Double)
    extra: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    """Sections kept verbatim (canonical units): bit records, cores, logs, perfs, well tests."""

    __table_args__ = (
        UniqueConstraint("wellbore_id", "start_at"),
        CheckConstraint("end_at > start_at", name="period"),
    )


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = _pk()
    report_id: Mapped[int] = _report_fk()
    wellbore_id: Mapped[int] = mapped_column(ForeignKey("wellbores.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(SmallInteger)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_h: Mapped[float | None] = mapped_column(Double)
    md_m: Mapped[float | None] = mapped_column(Double)
    phase: Mapped[str | None] = mapped_column(String(32))
    proprietary_code: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str | None] = mapped_column(String(16))
    state_detail: Mapped[str | None] = mapped_column(String(64))
    comments: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("report_id", "seq"),
        Index("ix_activities_wellbore_start", "wellbore_id", "start_at"),
        Index("ix_activities_code", "proprietary_code"),
        Index("ix_activities_state_detail", "state_detail"),
    )


class Fluid(Base):
    __tablename__ = "fluids"

    id: Mapped[int] = _pk()
    report_id: Mapped[int] = _report_fk()
    seq: Mapped[int] = mapped_column(SmallInteger)
    at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    md_m: Mapped[float | None] = mapped_column(Double)
    fluid_type: Mapped[str | None] = mapped_column(String(64))
    mud_class: Mapped[str | None] = mapped_column(String(32))
    location_sample: Mapped[str | None] = mapped_column(String(64))
    density_gcc: Mapped[float | None] = mapped_column(Double)
    vis_funnel_s: Mapped[float | None] = mapped_column(Double)
    pv_mpas: Mapped[float | None] = mapped_column(Double)
    yp_pa: Mapped[float | None] = mapped_column(Double)
    pres_bop_rating_kpa: Mapped[float | None] = mapped_column(Double)
    temp_hthp_degc: Mapped[float | None] = mapped_column(Double)
    filtrate_ltlp_m3: Mapped[float | None] = mapped_column(Double)
    filter_cake_ltlp_m: Mapped[float | None] = mapped_column(Double)

    __table_args__ = (UniqueConstraint("report_id", "seq"),)


class SurveyStation(Base):
    """Survey stations exactly as reported (the trajectory is derived from these)."""

    __tablename__ = "survey_stations"

    id: Mapped[int] = _pk()
    report_id: Mapped[int] = _report_fk()
    seq: Mapped[int] = mapped_column(SmallInteger)
    at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    md_m: Mapped[float | None] = mapped_column(Double)
    tvd_m: Mapped[float | None] = mapped_column(Double)
    incl_deg: Mapped[float | None] = mapped_column(Double)
    azi_deg: Mapped[float | None] = mapped_column(Double)

    __table_args__ = (UniqueConstraint("report_id", "seq"),)


class PorePressure(Base):
    __tablename__ = "pore_pressures"

    id: Mapped[int] = _pk()
    report_id: Mapped[int] = _report_fk()
    seq: Mapped[int] = mapped_column(SmallInteger)
    at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    md_m: Mapped[float | None] = mapped_column(Double)
    emw_gcc: Mapped[float | None] = mapped_column(Double)
    reading_kind: Mapped[str | None] = mapped_column(String(32))

    __table_args__ = (UniqueConstraint("report_id", "seq"),)


class LithologyShow(Base):
    __tablename__ = "lithology_shows"

    id: Mapped[int] = _pk()
    report_id: Mapped[int] = _report_fk()
    seq: Mapped[int] = mapped_column(SmallInteger)
    at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    md_top_m: Mapped[float | None] = mapped_column(Double)
    md_bottom_m: Mapped[float | None] = mapped_column(Double)
    tvd_top_m: Mapped[float | None] = mapped_column(Double)
    tvd_bottom_m: Mapped[float | None] = mapped_column(Double)
    lithology: Mapped[str | None] = mapped_column(Text)
    show: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("report_id", "seq"),)


class StratPick(Base):
    """Formation tops as picked in a daily report (`stratInfo`), before resolution."""

    __tablename__ = "strat_picks"

    id: Mapped[int] = _pk()
    report_id: Mapped[int] = _report_fk()
    seq: Mapped[int] = mapped_column(SmallInteger)
    at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    md_top_m: Mapped[float | None] = mapped_column(Double)
    tvd_top_m: Mapped[float | None] = mapped_column(Double)
    description: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("report_id", "seq"),)


class GasReading(Base):
    __tablename__ = "gas_readings"

    id: Mapped[int] = _pk()
    report_id: Mapped[int] = _report_fk()
    seq: Mapped[int] = mapped_column(SmallInteger)
    at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reading_type: Mapped[str | None] = mapped_column(String(32))
    md_top_m: Mapped[float | None] = mapped_column(Double)
    tvd_top_m: Mapped[float | None] = mapped_column(Double)
    gas_high_pct: Mapped[float | None] = mapped_column(Double)
    methane_ppm: Mapped[float | None] = mapped_column(Double)
    ethane_ppm: Mapped[float | None] = mapped_column(Double)
    propane_ppm: Mapped[float | None] = mapped_column(Double)
    ibutane_ppm: Mapped[float | None] = mapped_column(Double)
    nbutane_ppm: Mapped[float | None] = mapped_column(Double)
    ipentane_ppm: Mapped[float | None] = mapped_column(Double)

    __table_args__ = (UniqueConstraint("report_id", "seq"),)


class CasingString(Base):
    __tablename__ = "casing_strings"

    id: Mapped[int] = _pk()
    report_id: Mapped[int] = _report_fk()
    seq: Mapped[int] = mapped_column(SmallInteger)
    string_type: Mapped[str | None] = mapped_column(String(8))
    outer_diameter_m: Mapped[float | None] = mapped_column(Double)
    inner_diameter_m: Mapped[float | None] = mapped_column(Double)
    weight_kgpm: Mapped[float | None] = mapped_column(Double)
    grade: Mapped[str | None] = mapped_column(String(32))
    connection: Mapped[str | None] = mapped_column(String(64))
    length_m: Mapped[float | None] = mapped_column(Double)
    md_top_m: Mapped[float | None] = mapped_column(Double)
    md_bottom_m: Mapped[float | None] = mapped_column(Double)
    casing_type: Mapped[str | None] = mapped_column(String(64))
    run_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_description: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("report_id", "seq"),)


class EquipmentFailure(Base):
    __tablename__ = "equipment_failures"

    id: Mapped[int] = _pk()
    report_id: Mapped[int] = _report_fk()
    seq: Mapped[int] = mapped_column(SmallInteger)
    at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    md_m: Mapped[float | None] = mapped_column(Double)
    equip_class: Mapped[str | None] = mapped_column(String(128))
    missed_production_h: Mapped[float | None] = mapped_column(Double)
    repaired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    description: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("report_id", "seq"),)


class TrajectoryStation(Base):
    """Reconciled trajectory (derived). Offsets are from the well's surface location."""

    __tablename__ = "trajectory_stations"

    id: Mapped[int] = _pk()
    wellbore_id: Mapped[int] = mapped_column(ForeignKey("wellbores.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    md_m: Mapped[float] = mapped_column(Double)
    tvd_m: Mapped[float] = mapped_column(Double)
    tvdss_m: Mapped[float | None] = mapped_column(Double)
    incl_deg: Mapped[float] = mapped_column(Double)
    azi_deg: Mapped[float] = mapped_column(Double)
    north_m: Mapped[float] = mapped_column(Double)
    east_m: Mapped[float] = mapped_column(Double)
    easting_m: Mapped[float] = mapped_column(Double)
    northing_m: Mapped[float] = mapped_column(Double)
    dls_deg_per_30m: Mapped[float] = mapped_column(Double)
    tvd_mincurv_m: Mapped[float] = mapped_column(Double)
    tvd_reported_m: Mapped[float | None] = mapped_column(Double)
    tvd_source: Mapped[str] = mapped_column(String(16))
    """`reported`, `adjusted` or `min_curvature` (see `drillsage.domain.trajectory`)."""
    reported_tvd_rejected: Mapped[bool] = mapped_column(Boolean)
    inherited: Mapped[bool] = mapped_column(Boolean)

    __table_args__ = (
        UniqueConstraint("wellbore_id", "seq"),
        UniqueConstraint("wellbore_id", "md_m"),
    )


class FormationTop(Base):
    """Resolved formation/group tops per wellbore (derived from Sodir and DDR picks)."""

    __tablename__ = "formation_tops"

    id: Mapped[int] = _pk()
    wellbore_id: Mapped[int] = mapped_column(ForeignKey("wellbores.id", ondelete="CASCADE"))
    basin_pack: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(64))
    level: Mapped[str] = mapped_column(String(16))
    md_top_m: Mapped[float] = mapped_column(Double)
    tvd_top_m: Mapped[float | None] = mapped_column(Double)
    tvdss_top_m: Mapped[float | None] = mapped_column(Double)
    source: Mapped[str] = mapped_column(String(16))
    """`sodir`, `ddr` or `correlated` (see `drillsage.domain.formations.TopSource`)."""
    raw_name: Mapped[str] = mapped_column(String(128))
    inherited_from_id: Mapped[int | None] = mapped_column(
        ForeignKey("wellbores.id", ondelete="CASCADE")
    )
    """Set when a sidetrack inherits the top from its parent hole above the kick-off."""

    __table_args__ = (
        UniqueConstraint("wellbore_id", "name", "level"),
        Index("ix_formation_tops_name", "name"),
    )


class Event(Base):
    """A drilling problem episode extracted from daily reports (Phase 2).

    One row per extractor tier: the rule tier is rebuilt deterministically; later tiers
    (`llm`, `rule+llm`, `human`) are merged by `drillsage.extract.merge`.
    """

    __tablename__ = "events"

    id: Mapped[int] = _pk()
    wellbore_id: Mapped[int] = mapped_column(ForeignKey("wellbores.id", ondelete="CASCADE"))
    hazard: Mapped[str] = mapped_column(String(32))
    subtype: Mapped[str | None] = mapped_column(String(64))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    md_top_m: Mapped[float | None] = mapped_column(Double)
    md_bottom_m: Mapped[float | None] = mapped_column(Double)
    depth_source: Mapped[str] = mapped_column(String(16))
    tvd_top_m: Mapped[float | None] = mapped_column(Double)
    tvd_bottom_m: Mapped[float | None] = mapped_column(Double)
    tvdss_top_m: Mapped[float | None] = mapped_column(Double)
    tvdss_bottom_m: Mapped[float | None] = mapped_column(Double)
    formation: Mapped[str | None] = mapped_column(String(64))
    formation_group: Mapped[str | None] = mapped_column(String(64))
    formation_source: Mapped[str | None] = mapped_column(String(16))
    hole_diameter_m: Mapped[float | None] = mapped_column(Double)
    mud_density_gcc: Mapped[float | None] = mapped_column(Double)
    mud_class: Mapped[str | None] = mapped_column(String(32))
    severity: Mapped[int] = mapped_column(SmallInteger)
    npt_h: Mapped[float] = mapped_column(Double)
    led_to_sidetrack: Mapped[bool] = mapped_column(Boolean)
    detected_by: Mapped[str] = mapped_column(String(16))
    confidence_tier: Mapped[str] = mapped_column(String(16))
    extractor_version: Mapped[str] = mapped_column(String(32))
    n_activities: Mapped[int] = mapped_column(Integer)
    mitigations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    """`[{action, outcome, activity_id, span, outcome_activity_id, outcome_span}]`."""

    __table_args__ = (
        CheckConstraint("severity BETWEEN 1 AND 4", name="severity"),
        CheckConstraint("npt_h >= 0", name="npt"),
        CheckConstraint(
            "confidence_tier IN ('rule', 'llm', 'rule+llm', 'human')", name="confidence_tier"
        ),
        Index("ix_events_wellbore_hazard", "wellbore_id", "hazard"),
        Index("ix_events_formation", "formation"),
        Index("ix_events_tier", "confidence_tier"),
    )


class EventEvidence(Base):
    """Why an event exists: the activity and, for text, the exact character span."""

    __tablename__ = "event_evidence"

    id: Mapped[int] = _pk()
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    """`code`, `trigger`, `mitigation` or `outcome`."""
    rule_id: Mapped[str] = mapped_column(String(64))
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    """Half-open span into `activities.comments`; null for code evidence."""

    __table_args__ = (
        CheckConstraint(
            "(char_start IS NULL AND char_end IS NULL)"
            " OR (char_start >= 0 AND char_end > char_start)",
            name="span",
        ),
    )


class LLMCall(Base):
    """Budget ledger: one row per model call (cached results cost nothing and are not logged)."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = _pk()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    purpose: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(64))
    served_model: Mapped[str | None] = mapped_column(String(64))
    """The model that actually answered (differs when a refusal fallback ran)."""
    cache_key: Mapped[str] = mapped_column(String(64), index=True)
    batch: Mapped[bool] = mapped_column(Boolean)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cache_creation_input_tokens: Mapped[int] = mapped_column(Integer)
    cache_read_input_tokens: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[float] = mapped_column(Double)
    stop_reason: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    """`ok`, `refused`, `truncated`, `invalid` or `error`."""
    request_id: Mapped[str | None] = mapped_column(String(128))

    __table_args__ = (CheckConstraint("cost_usd >= 0", name="cost"),)


class LLMResult(Base):
    """Validated model output keyed by the hash of everything that determines it."""

    __tablename__ = "llm_results"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    purpose: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(32))
    output: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LLMExtraction(Base):
    """Which cached result holds the LLM extraction for each daily report."""

    __tablename__ = "llm_extractions"

    report_id: Mapped[int] = mapped_column(
        ForeignKey("daily_reports.id", ondelete="CASCADE"), primary_key=True
    )
    prompt_version: Mapped[str] = mapped_column(String(32), primary_key=True)
    cache_key: Mapped[str] = mapped_column(ForeignKey("llm_results.cache_key", ondelete="CASCADE"))
    rejected_quotes: Mapped[int] = mapped_column(Integer)
    """Evidence quotes that did not match the source text and were dropped."""
