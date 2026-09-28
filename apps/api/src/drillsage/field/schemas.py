"""The field snapshot: everything the web cockpit shows about one field, in one document.

It is derived data (rebuilt by `drillsage-data snapshot`, never edited) and is served as-is by
`GET /api/v1/field`, so these models are both the file format and the API contract.
Depths are metres, densities g/cm³, durations hours; TVDSS is positive below mean sea level.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

SNAPSHOT_VERSION = "field-snapshot-v1"


class _Out(BaseModel):
    model_config = ConfigDict(frozen=True)


class FieldStats(_Out):
    wellbores: int
    reports: int
    activities: int
    events: int
    geological_events: int
    npt_h: float
    evidence_spans: int
    first_report_on: date
    last_report_on: date


class HazardSummary(_Out):
    hazard: str
    geological: bool
    events: int
    npt_h: float
    wellbores: int


class FormationUnit(_Out):
    """A unit of the basin pack that appears in this field, in stratigraphic order."""

    name: str
    level: Literal["group", "formation"]
    order: int


class TrajectoryPoint(_Out):
    md_m: float
    tvdss_m: float
    easting_m: float
    northing_m: float


class TopOut(_Out):
    name: str
    level: Literal["group", "formation"]
    md_top_m: float
    tvdss_top_m: float | None
    source: str


class OffsetOut(_Out):
    """Another wellbore of the field, as an offset for this one."""

    name: str
    surface_distance_m: float
    completed_before_spud: bool
    """Its last report predates this wellbore's first one, so it is usable without hindsight.

    First reports are used rather than spud dates because Volve sidetracks carry their parent's
    spud date.
    """


class WellboreOut(_Out):
    name: str
    well_name: str
    kind: str
    parent_name: str | None
    purpose: str | None
    era: Literal["exploration", "development"]
    lat_deg: float
    lon_deg: float
    easting_m: float
    northing_m: float
    utm_epsg: int
    kb_elevation_m: float | None
    water_depth_m: float | None
    td_md_m: float
    td_tvdss_m: float | None
    spud_at: datetime | None
    completed_on: date | None
    first_report_at: datetime
    last_report_at: datetime
    reports: int
    events: int
    npt_h: float
    trajectory: list[TrajectoryPoint]
    tops: list[TopOut]
    offsets: list[OffsetOut]


class SpanOut(_Out):
    start: int
    end: int
    kind: str
    rule_id: str


class EvidenceLine(_Out):
    """One report line behind an event, with the character spans that triggered it."""

    report_on: date
    line: int
    at: datetime
    md_m: float | None
    code: str | None
    text: str
    spans: list[SpanOut]


class MitigationOut(_Out):
    action: str
    outcome: str


class EventOut(_Out):
    id: int
    wellbore: str
    hazard: str
    geological: bool
    subtype: str | None
    start_at: datetime
    end_at: datetime
    md_top_m: float | None
    md_bottom_m: float | None
    depth_source: str
    tvdss_top_m: float | None
    tvdss_bottom_m: float | None
    easting_m: float | None
    northing_m: float | None
    formation: str | None
    formation_group: str | None
    mud_density_gcc: float | None
    hole_diameter_m: float | None
    severity: int
    npt_h: float
    led_to_sidetrack: bool
    detected_by: str
    confidence_tier: str
    evidence: list[EvidenceLine]
    evidence_lines_total: int
    mitigations: list[MitigationOut]


class FieldSnapshot(_Out):
    version: str
    generated_at: datetime
    field: str
    basin_pack: str
    extractor_version: str
    attribution: str
    stats: FieldStats
    hazards: list[HazardSummary]
    formations: list[FormationUnit]
    wellbores: list[WellboreOut]
    events: list[EventOut]


class EventPoint(_Out):
    """An event without its evidence: enough to draw it on the map and the depth strip."""

    id: int
    wellbore: str
    hazard: str
    geological: bool
    start_at: datetime
    md_top_m: float | None
    tvdss_top_m: float | None
    easting_m: float | None
    northing_m: float | None
    formation: str | None
    severity: int
    npt_h: float


class FieldOverview(_Out):
    """The snapshot without evidence text: the payload of every map and depth view."""

    version: str
    generated_at: datetime
    field: str
    basin_pack: str
    extractor_version: str
    attribution: str
    stats: FieldStats
    hazards: list[HazardSummary]
    formations: list[FormationUnit]
    wellbores: list[WellboreOut]
    events: list[EventPoint]


class EventPage(_Out):
    total: int
    offset: int
    limit: int
    npt_h: float
    """Total NPT of every matching event, not only this page."""
    items: list[EventOut]
