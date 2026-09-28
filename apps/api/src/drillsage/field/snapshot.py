"""Build the field snapshot straight from the raw sources, with no database.

The same code as the database pipeline does the work (parser, registry, minimum-curvature
trajectories, formation tops, rule-tier extraction); only the storage is skipped. The web
cockpit can therefore show real data on any machine that has run `make data-fetch`.

Events here come from the rule tier only: LLM results live in the database, so a snapshot
built from raw files cannot include them. `extractor_version` says which tiers are present.
"""

import bisect
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from drillsage.core.basin_packs import load_basin_pack
from drillsage.core.config import VOLVE_ATTRIBUTION
from drillsage.domain import trajectory as traj
from drillsage.domain.formations import FormationTop, StratLevel, unit_at_md
from drillsage.domain.hazards import HazardType, is_geological
from drillsage.extract.episodes import ActivityRecord, Event, extract_events
from drillsage.extract.rules import RULES_VERSION
from drillsage.field.schemas import (
    SNAPSHOT_VERSION,
    EventOut,
    EvidenceLine,
    FieldSnapshot,
    FieldStats,
    FormationUnit,
    HazardSummary,
    MitigationOut,
    OffsetOut,
    SpanOut,
    TopOut,
    TrajectoryPoint,
    WellboreOut,
)
from drillsage.ingest.pipeline import (
    compose_trajectory,
    final_tops,
    own_tops,
    read_sources,
    surface_location,
)
from drillsage.ingest.registry import WellboreRecord
from drillsage.ingest.witsml_ddr import DrillReport

SNAPSHOT_PATH: Final = Path("processed") / "web" / "field-snapshot.json"
"""Relative to the data directory."""

MAX_EVIDENCE_LINES: Final = 12
"""Per event; long fishing jobs cite dozens of lines, and the total is reported alongside."""

DEVELOPMENT_ERA_FROM_YEAR: Final = 2000


@dataclass(frozen=True, slots=True)
class _Report:
    id: int
    wellbore: str
    report: DrillReport


@dataclass(frozen=True, slots=True)
class _Line:
    report: _Report
    seq: int
    record: ActivityRecord


def _reports(files_reports: Sequence[DrillReport]) -> list[_Report]:
    """Unique reports per wellbore and period (a period loaded twice is kept once, as in the DB)."""
    seen: set[tuple[str, datetime | None]] = set()
    out: list[_Report] = []
    for report in files_reports:
        key = (report.wellbore_name, report.start_at)
        if key in seen:
            continue
        seen.add(key)
        out.append(_Report(id=len(out) + 1, wellbore=report.wellbore_name, report=report))
    return out


def _lines(reports: Sequence[_Report]) -> list[_Line]:
    lines: list[_Line] = []
    for rep in reports:
        report_md = rep.report.status.md_m if rep.report.status else None
        for seq, activity in enumerate(rep.report.activities):
            if activity.start_at is None or activity.end_at is None:
                continue
            record = ActivityRecord(
                id=len(lines) + 1,
                wellbore=rep.wellbore,
                report_id=rep.id,
                seq=seq,
                start_at=activity.start_at,
                end_at=activity.end_at,
                md_m=activity.md_m,
                report_md_m=report_md,
                proprietary_code=activity.proprietary_code,
                state=activity.state,
                state_detail=activity.state_detail,
                comments=activity.comments,
            )
            lines.append(_Line(report=rep, seq=seq, record=record))
    # The extractor expects the database order: wellbore, start time, id.
    lines.sort(key=lambda ln: (ln.record.wellbore, ln.record.start_at, ln.record.id))
    return lines


def _stations(reports: Sequence[_Report]) -> dict[str, list[traj.SurveyStation]]:
    stations: dict[str, list[traj.SurveyStation]] = defaultdict(list)
    for rep in reports:
        for s in rep.report.survey_stations:
            if s.md_m is not None and s.incl_deg is not None and s.azi_deg is not None:
                stations[rep.wellbore].append(
                    traj.SurveyStation(
                        md_m=s.md_m,
                        incl_deg=s.incl_deg,
                        azi_deg=s.azi_deg,
                        tvd_reported_m=s.tvd_m,
                        measured_at=s.at,
                    )
                )
    return stations


def _picks(reports: Sequence[_Report]) -> dict[str, list[tuple[str, float]]]:
    picks: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for rep in reports:
        for top in rep.report.strat_tops:
            if top.description and top.md_top_m is not None:
                picks[rep.wellbore].append((top.description, top.md_top_m))
    return picks


def plan_position(stations: Sequence[traj.TrajectoryStation], md_m: float) -> tuple[float, float]:
    """(north, east) offset from the wellhead at `md_m`, linear between stations."""
    mds = [s.md_m for s in stations]
    i = bisect.bisect_right(mds, md_m) - 1
    if i < 0:
        return stations[0].north_m, stations[0].east_m
    if i >= len(stations) - 1:
        return stations[-1].north_m, stations[-1].east_m
    a, b = stations[i], stations[i + 1]
    f = (md_m - a.md_m) / (b.md_m - a.md_m)
    return a.north_m + f * (b.north_m - a.north_m), a.east_m + f * (b.east_m - a.east_m)


def _tvdss(trajectory: traj.Trajectory, kb_m: float | None, md_m: float | None) -> float | None:
    if md_m is None or kb_m is None:
        return None
    return trajectory.tvd_at_md(md_m) - kb_m


def _r(value: float | None, digits: int = 1) -> float | None:
    return round(value, digits) if value is not None else None


def _density(rep: _Report) -> float | None:
    return next((f.density_gcc for f in rep.report.fluids if f.density_gcc is not None), None)


def _mud_density(
    event: Event, own_report: _Report, wellbore_reports: list[_Report]
) -> float | None:
    """Mud density sampled in the event's report, else in the latest report before the event."""
    density = _density(own_report)
    if density is not None:
        return density
    earlier = [
        r for r in wellbore_reports if r.report.start_at and r.report.start_at <= event.start_at
    ]
    return next((d for r in reversed(earlier) if (d := _density(r)) is not None), None)


def _evidence(event: Event, lines_by_id: dict[int, _Line]) -> tuple[list[EvidenceLine], int]:
    grouped: dict[int, list[SpanOut]] = {}
    for ev in event.evidence:
        spans = grouped.setdefault(ev.activity_id, [])
        if ev.span is not None:
            spans.append(
                SpanOut(
                    start=ev.span.start, end=ev.span.end, kind=ev.kind.value, rule_id=ev.rule_id
                )
            )
    out = []
    for activity_id, spans in list(grouped.items())[:MAX_EVIDENCE_LINES]:
        line = lines_by_id[activity_id]
        start = line.report.report.start_at
        out.append(
            EvidenceLine(
                report_on=(start or line.record.start_at).date(),
                line=line.seq,
                at=line.record.start_at,
                md_m=_r(line.record.md_m),
                code=line.record.proprietary_code,
                text=line.record.comments or "",
                spans=sorted(spans, key=lambda s: s.start),
            )
        )
    return out, len(grouped)


def _formation(tops: Sequence[FormationTop], md: float | None) -> tuple[str | None, str | None]:
    if md is None:
        return None, None
    formation = unit_at_md(tops, md, StratLevel.FORMATION)
    group = unit_at_md(tops, md, StratLevel.GROUP)
    return (formation.name if formation else None, group.name if group else None)


def _era(record: WellboreRecord) -> str:
    year = (record.spud_at or record.first_report_at).year
    return "development" if year >= DEVELOPMENT_ERA_FROM_YEAR else "exploration"


def build_snapshot(data_dir: Path, basin_pack: str, *, field: str = "Volve") -> FieldSnapshot:
    pack = load_basin_pack(basin_pack)
    bundle = read_sources(data_dir)
    registry = bundle.registry
    reports = _reports([r for f in bundle.ddr_files for r in f.reports])
    reports_by_id = {rep.id: rep for rep in reports}
    reports_by_wellbore: dict[str, list[_Report]] = defaultdict(list)
    for rep in sorted(reports, key=lambda r: r.report.start_at or datetime.min.replace(tzinfo=UTC)):
        reports_by_wellbore[rep.wellbore].append(rep)

    stations = _stations(reports)
    computed = {name: compose_trajectory(registry, stations, name) for name in registry}
    trajectories = {name: traj.Trajectory(st) for name, st in computed.items()}
    own, _ = own_tops(registry, _picks(reports), bundle.sodir_tops, pack)
    tops = final_tops(registry, own, trajectories)

    lines = _lines(reports)
    lines_by_id = {ln.record.id: ln for ln in lines}
    max_md: dict[str, float] = {}
    for rep in reports:
        md = rep.report.status.md_m if rep.report.status else None
        if md is not None:
            max_md[rep.wellbore] = max(md, max_md.get(rep.wellbore, 0.0))
    mudline = {
        name: r.kb_elevation_m + r.water_depth_m
        for name, r in registry.items()
        if r.kb_elevation_m is not None and r.water_depth_m is not None
    }
    events = extract_events([ln.record for ln in lines], max_md, mudline)

    event_rows: list[EventOut] = []
    for i, event in enumerate(events, start=1):
        record = registry[event.wellbore]
        kb = record.kb_elevation_m
        trajectory = trajectories[event.wellbore]
        surface = surface_location(record)

        position = (
            plan_position(computed[event.wellbore], event.md_top_m)
            if event.md_top_m is not None
            else None
        )
        formation, group = _formation(tops[event.wellbore], event.md_top_m)
        evidence, total = _evidence(event, lines_by_id)
        status = reports_by_id[event.report_id].report.status
        event_rows.append(
            EventOut(
                id=i,
                wellbore=event.wellbore,
                hazard=event.hazard.value,
                geological=is_geological(event.hazard),
                subtype=event.subtype,
                start_at=event.start_at,
                end_at=event.end_at,
                md_top_m=_r(event.md_top_m),
                md_bottom_m=_r(event.md_bottom_m),
                depth_source=event.depth_source,
                tvdss_top_m=_r(_tvdss(trajectory, kb, event.md_top_m)),
                tvdss_bottom_m=_r(_tvdss(trajectory, kb, event.md_bottom_m)),
                easting_m=_r(surface.easting_m + position[1]) if position else None,
                northing_m=_r(surface.northing_m + position[0]) if position else None,
                formation=formation,
                formation_group=group,
                mud_density_gcc=_r(
                    _mud_density(
                        event,
                        reports_by_id[event.report_id],
                        reports_by_wellbore[event.wellbore],
                    ),
                    3,
                ),
                hole_diameter_m=_r(status.hole_diameter_m if status else None, 4),
                severity=event.severity,
                npt_h=round(event.npt_h, 2),
                led_to_sidetrack=event.led_to_sidetrack,
                detected_by=event.detected_by,
                confidence_tier=event.confidence_tier,
                evidence=evidence,
                evidence_lines_total=total,
                mitigations=[
                    MitigationOut(action=m.action, outcome=m.outcome.value)
                    for m in event.mitigations
                ],
            )
        )

    wellbores = _wellbores(
        registry,
        computed=computed,
        trajectories=trajectories,
        tops=tops,
        reports_by_wellbore=reports_by_wellbore,
        events=event_rows,
    )
    return FieldSnapshot(
        version=SNAPSHOT_VERSION,
        generated_at=datetime.now(UTC),
        field=field,
        basin_pack=pack.key,
        extractor_version=RULES_VERSION,
        attribution=VOLVE_ATTRIBUTION,
        stats=_stats(
            reports,
            lines,
            event_rows,
            wellbores,
            evidence_spans=sum(1 for e in events for ev in e.evidence if ev.span is not None),
        ),
        hazards=_hazards(event_rows),
        formations=_formations(pack.key, tops),
        wellbores=wellbores,
        events=event_rows,
    )


def _wellbores(
    registry: dict[str, WellboreRecord],
    *,
    computed: dict[str, list[traj.TrajectoryStation]],
    trajectories: dict[str, traj.Trajectory],
    tops: dict[str, list[FormationTop]],
    reports_by_wellbore: dict[str, list[_Report]],
    events: Sequence[EventOut],
) -> list[WellboreOut]:
    surfaces = {name: surface_location(r) for name, r in registry.items()}
    out = []
    for name, record in sorted(registry.items()):
        kb = record.kb_elevation_m
        surface = surfaces[name]
        report_mds = [
            r.report.status.md_m
            for r in reports_by_wellbore[name]
            if r.report.status and r.report.status.md_m is not None
        ]
        td = max([*report_mds, record.total_depth_md_m or 0.0, trajectories[name].max_md_m])
        mine = [e for e in events if e.wellbore == name]
        offsets = [
            OffsetOut(
                name=other,
                surface_distance_m=round(
                    (
                        (surfaces[other].easting_m - surface.easting_m) ** 2
                        + (surfaces[other].northing_m - surface.northing_m) ** 2
                    )
                    ** 0.5,
                    1,
                ),
                completed_before_spud=other_record.last_report_at <= record.first_report_at,
            )
            for other, other_record in sorted(registry.items())
            if other != name
        ]
        out.append(
            WellboreOut(
                name=name,
                well_name=record.well_name,
                kind=record.kind,
                parent_name=record.parent_name,
                purpose=record.purpose,
                era="development" if _era(record) == "development" else "exploration",
                lat_deg=round(surface.lat_deg, 6),
                lon_deg=round(surface.lon_deg, 6),
                easting_m=round(surface.easting_m, 1),
                northing_m=round(surface.northing_m, 1),
                utm_epsg=surface.utm_epsg,
                kb_elevation_m=kb,
                water_depth_m=record.water_depth_m,
                td_md_m=round(td, 1),
                td_tvdss_m=_r(trajectories[name].tvd_at_md(td) - kb) if kb is not None else None,
                spud_at=record.spud_at,
                completed_on=record.completed_on,
                first_report_at=record.first_report_at,
                last_report_at=record.last_report_at,
                reports=len(reports_by_wellbore[name]),
                events=len(mine),
                npt_h=round(sum(e.npt_h for e in mine), 1),
                trajectory=[
                    TrajectoryPoint(
                        md_m=round(s.md_m, 1),
                        tvdss_m=round(s.tvd_m - kb, 1) if kb is not None else round(s.tvd_m, 1),
                        easting_m=round(surface.easting_m + s.east_m, 1),
                        northing_m=round(surface.northing_m + s.north_m, 1),
                    )
                    for s in computed[name]
                ],
                tops=[
                    TopOut(
                        name=t.name,
                        level="group" if t.level == StratLevel.GROUP else "formation",
                        md_top_m=round(t.md_top_m, 1),
                        tvdss_top_m=(
                            _r(trajectories[name].tvd_at_md(t.md_top_m) - kb)
                            if kb is not None
                            else None
                        ),
                        source=t.source.value,
                    )
                    for t in tops[name]
                ],
                offsets=sorted(offsets, key=lambda o: o.surface_distance_m),
            )
        )
    return out


def _stats(
    reports: Sequence[_Report],
    lines: Sequence[_Line],
    events: Sequence[EventOut],
    wellbores: Sequence[WellboreOut],
    *,
    evidence_spans: int,
) -> FieldStats:
    days = [r.report.start_at.date() for r in reports if r.report.start_at is not None]
    return FieldStats(
        wellbores=len(wellbores),
        reports=len(reports),
        activities=len(lines),
        events=len(events),
        geological_events=sum(e.geological for e in events),
        npt_h=round(sum(e.npt_h for e in events), 1),
        evidence_spans=evidence_spans,
        first_report_on=min(days),
        last_report_on=max(days),
    )


def _hazards(events: Sequence[EventOut]) -> list[HazardSummary]:
    return [
        HazardSummary(
            hazard=hazard.value,
            geological=is_geological(hazard),
            events=len(mine := [e for e in events if e.hazard == hazard.value]),
            npt_h=round(sum(e.npt_h for e in mine), 1),
            wellbores=len({e.wellbore for e in mine}),
        )
        for hazard in HazardType
    ]


def _formations(pack_key: str, tops: dict[str, list[FormationTop]]) -> list[FormationUnit]:
    pack = load_basin_pack(pack_key)
    present = {(t.name, t.level) for wb in tops.values() for t in wb}
    units = [u for u in pack.units if (u.name, u.level) in present]
    return [
        FormationUnit(
            name=u.name,
            level="group" if u.level == StratLevel.GROUP else "formation",
            order=pack.order(u),
        )
        for u in sorted(units, key=pack.order)
    ]


def write_snapshot(snapshot: FieldSnapshot, data_dir: Path) -> Path:
    path = data_dir / SNAPSHOT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(snapshot.model_dump_json(), encoding="utf-8")
    tmp.replace(path)  # atomic: the API never reads a half-written file
    return path


def read_snapshot(data_dir: Path) -> FieldSnapshot:
    return FieldSnapshot.model_validate(
        json.loads((data_dir / SNAPSHOT_PATH).read_text(encoding="utf-8"))
    )


__all__ = [
    "SNAPSHOT_PATH",
    "build_snapshot",
    "plan_position",
    "read_snapshot",
    "write_snapshot",
]
