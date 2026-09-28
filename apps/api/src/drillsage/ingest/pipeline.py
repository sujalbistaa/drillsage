"""Load raw sources into the canonical model, idempotently.

Steps:
1. Parse every DDR file and the Sodir tables (pure, in memory; ~2 s for Volve).
2. Upsert wells and wellbores from the reconciled registry.
3. Insert each DDR file not ingested before (keyed by SHA-256) in its own transaction.
4. Rebuild derived tables (trajectories, formation tops) from what is in the database.

Running it twice changes nothing: files are skipped by hash, upserts converge, and derived
tables are recomputed deterministically.
"""

import hashlib
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from drillsage.core.basin_packs import load_basin_pack
from drillsage.core.logging import get_logger
from drillsage.db import models as m
from drillsage.db.base import Base
from drillsage.domain import trajectory as traj
from drillsage.domain.formations import (
    BasinPack,
    FormationTop,
    TopSource,
    consolidate_tops,
    correlate_tops,
    field_median_tvdss,
    inherit_from_parent,
    resolve_top,
)
from drillsage.ingest.fetch import DDR_MIRROR_DIR, SODIR_DIR
from drillsage.ingest.georef import SurfaceLocation, to_wgs84
from drillsage.ingest.registry import (
    DdrWellboreSummary,
    WellboreRecord,
    ancestry,
    build_registry,
    mode,
)
from drillsage.ingest.sodir import (
    SodirLithoTop,
    SodirWellbore,
    parse_litho_tops,
    parse_wellbores,
)
from drillsage.ingest.witsml_ddr import DrillReport, parse_ddr

log = get_logger(__name__)

PARSER_VERSION: Final = "ddr-1.0.0"


@dataclass(frozen=True, slots=True)
class DdrFile:
    relative_path: str
    sha256: str
    size_bytes: int
    reports: tuple[DrillReport, ...]


@dataclass(frozen=True, slots=True)
class SourceBundle:
    ddr_files: tuple[DdrFile, ...]
    registry: dict[str, WellboreRecord]
    sodir_tops: tuple[SodirLithoTop, ...]


@dataclass
class IngestStats:
    files_seen: int = 0
    files_ingested: int = 0
    files_skipped: int = 0
    reports_conflicting: list[str] = field(default_factory=list)
    wellbores: int = 0
    trajectory_stations: int = 0
    formation_tops: int = 0
    unresolved_formation_names: dict[str, int] = field(default_factory=dict)


def ddr_paths(data_dir: Path) -> list[Path]:
    return sorted((data_dir / "raw" / DDR_MIRROR_DIR / "Reports").glob("*.xml"))


def read_sources(data_dir: Path) -> SourceBundle:
    """Parse all raw inputs. Raises if a file cannot be parsed (never skips silently)."""
    files: list[DdrFile] = []
    for path in ddr_paths(data_dir):
        data = path.read_bytes()
        parsed = parse_ddr(data)
        files.append(
            DdrFile(
                relative_path=path.relative_to(data_dir).as_posix(),
                sha256=hashlib.sha256(data).hexdigest(),
                size_bytes=len(data),
                reports=tuple(parsed.document.reports),
            )
        )
    if not files:
        raise FileNotFoundError(f"no DDR files under {data_dir}/raw; run `make data-fetch`")

    sodir_dir = data_dir / "raw" / SODIR_DIR
    sodir: list[SodirWellbore] = []
    for table in ("wellbore_exploration_all", "wellbore_development_all"):
        path = sodir_dir / f"{table}.csv"
        sodir.extend(parse_wellbores(path.read_text(encoding="utf-8-sig"), source=path.name))

    summaries = _summarise(files)
    registry = build_registry(summaries, sodir)
    npdids = {r.location.npdid for r in registry.values()}
    litho_path = sodir_dir / "strat_litho_wellbore.csv"
    tops = parse_litho_tops(
        litho_path.read_text(encoding="utf-8-sig"), source=litho_path.name, npdids=npdids
    )
    return SourceBundle(ddr_files=tuple(files), registry=registry, sodir_tops=tuple(tops))


def _summarise(files: Sequence[DdrFile]) -> dict[str, DdrWellboreSummary]:
    grouped: dict[str, list[DrillReport]] = defaultdict(list)
    for file in files:
        for report in file.reports:
            grouped[report.wellbore_name].append(report)
    summaries: dict[str, DdrWellboreSummary] = {}
    for name, reports in grouped.items():
        starts = [r.start_at for r in reports if r.start_at is not None]
        ends = [r.end_at for r in reports if r.end_at is not None]
        if not starts or not ends:
            raise ValueError(f"{name}: reports without a reporting period")
        infos = [r.wellbore_info for r in reports if r.wellbore_info is not None]
        statuses = [r.status for r in reports if r.status is not None]
        survey_mds = [
            s.md_m
            for r in reports
            for s in r.survey_stations
            if s.md_m is not None and s.incl_deg is not None and s.azi_deg is not None
        ]
        completes = [i.drill_complete_on for i in infos if i.drill_complete_on is not None]
        summaries[name] = DdrWellboreSummary(
            name=name,
            npdid=mode(r.npdid_wellbore for r in reports),
            spud_at=mode(i.spud_at for i in infos),
            drill_complete_on=max(completes) if completes else None,
            first_report_at=min(starts),
            last_report_at=max(ends),
            kickoff_md_m=mode(s.md_kickoff_m for s in statuses),
            first_survey_md_m=min(survey_mds) if survey_mds else None,
            operator=mode(i.operator for i in infos),
            rig_name=mode(
                a.name for i in infos for a in i.rig_aliases if a.naming_system == "NPD Name"
            ),
            elev_kelly_m=mode(s.elev_kelly_m for s in statuses if s.elev_kelly_m),
            water_depth_m=mode(s.water_depth_m for s in statuses),
        )
    return summaries


# ----------------------------------------------------------------------------- wells


def surface_location(record: WellboreRecord) -> SurfaceLocation:
    loc = record.location
    return to_wgs84(loc.lat_deg, loc.lon_deg, loc.geodetic_datum)


async def _upsert_wells(
    session: AsyncSession, registry: dict[str, WellboreRecord]
) -> dict[str, int]:
    by_well: dict[str, WellboreRecord] = {}
    for record in sorted(registry.values(), key=lambda r: r.name):
        by_well.setdefault(record.well_name, record)
    ids: dict[str, int] = {}
    for well_name, record in sorted(by_well.items()):
        surface = surface_location(record)
        values = {
            "name": well_name,
            "field": record.location.field,
            "surface_lat_deg": surface.lat_deg,
            "surface_lon_deg": surface.lon_deg,
            "surface_easting_m": surface.easting_m,
            "surface_northing_m": surface.northing_m,
            "utm_epsg": surface.utm_epsg,
            "source_datum": record.location.geodetic_datum,
            "source_lat_deg": record.location.lat_deg,
            "source_lon_deg": record.location.lon_deg,
        }
        stmt = (
            pg_insert(m.Well)
            .values(**values)
            .on_conflict_do_update(index_elements=[m.Well.name], set_=values)
            .returning(m.Well.id)
        )
        ids[well_name] = (await session.execute(stmt)).scalar_one()
    return ids


async def _upsert_wellbores(
    session: AsyncSession, registry: dict[str, WellboreRecord], well_ids: dict[str, int]
) -> dict[str, int]:
    ids: dict[str, int] = {}
    for record in sorted(registry.values(), key=lambda r: r.name):
        values = {
            "well_id": well_ids[record.well_name],
            "name": record.name,
            "npdid": record.npdid,
            "kind": record.kind,
            "purpose": record.purpose,
            "content": record.content,
            "operator": record.operator,
            "rig_name": record.rig_name,
            "kickoff_md_m": record.kickoff_md_m,
            "kb_elevation_m": record.kb_elevation_m,
            "water_depth_m": record.water_depth_m,
            "total_depth_md_m": record.total_depth_md_m,
            "final_tvd_m": record.final_tvd_m,
            "spud_at": record.spud_at,
            "completed_on": record.completed_on,
            "first_report_at": record.first_report_at,
            "last_report_at": record.last_report_at,
        }
        stmt = (
            pg_insert(m.Wellbore)
            .values(**values)
            .on_conflict_do_update(index_elements=[m.Wellbore.name], set_=values)
            .returning(m.Wellbore.id)
        )
        ids[record.name] = (await session.execute(stmt)).scalar_one()
    for record in registry.values():
        parent_id = ids[record.parent_name] if record.parent_name else None
        await session.execute(
            update(m.Wellbore).where(m.Wellbore.id == ids[record.name]).values(parent_id=parent_id)
        )
    return ids


# ----------------------------------------------------------------------------- reports


def _rows(items: Sequence[Any], **extra: object) -> list[dict[str, Any]]:
    return [{"seq": i, **extra, **item.model_dump()} for i, item in enumerate(items)]


def _report_values(report: DrillReport) -> dict[str, Any]:
    status = report.status
    info = report.wellbore_info
    values: dict[str, Any] = {
        "start_at": report.start_at,
        "end_at": report.end_at,
        "source_created_at": report.created_at,
        "operator": info.operator if info else None,
        "drill_contractor": info.drill_contractor if info else None,
        "days_ahead": info.days_ahead if info else None,
        "days_behind": info.days_behind if info else None,
        "rig_name": next(
            (a.name for a in (info.rig_aliases if info else []) if a.naming_system == "NPD Name"),
            None,
        ),
        "extra": {
            "status_at": status.at.isoformat() if status and status.at else None,
            "hole_diameter_start_at": (
                status.hole_diameter_start_at.isoformat()
                if status and status.hole_diameter_start_at
                else None
            ),
            "bit_records": [b.model_dump(mode="json") for b in report.bit_records],
            "core_info": [c.model_dump(mode="json") for c in report.core_info],
            "log_info": [x.model_dump(mode="json") for x in report.log_info],
            "well_tests": [w.model_dump(mode="json") for w in report.well_tests],
            "perforations": [p.model_dump(mode="json") for p in report.perforations],
        },
    }
    if status is not None:
        dumped = status.model_dump(exclude={"at", "hole_diameter_start_at"})
        values["report_no"] = dumped.pop("report_no")
        values.update(dumped)
    return values


async def _insert_report(
    session: AsyncSession, report: DrillReport, wellbore_id: int, source_file_id: int
) -> int:
    values = _report_values(report)
    report_id: int = (
        await session.execute(
            insert(m.DailyReport)
            .values(wellbore_id=wellbore_id, source_file_id=source_file_id, **values)
            .returning(m.DailyReport.id)
        )
    ).scalar_one()

    activities = [
        {
            **row,
            "duration_h": report.activities[row["seq"]].duration_h,
        }
        for row in _rows(report.activities, report_id=report_id, wellbore_id=wellbore_id)
    ]
    casing = [
        {
            "seq": i,
            "report_id": report_id,
            **c.model_dump(exclude={"run"}),
            "casing_type": c.run.casing_type if c.run else None,
            "run_start_at": c.run.start_at if c.run else None,
            "run_end_at": c.run.end_at if c.run else None,
            "run_description": c.run.description if c.run else None,
        }
        for i, c in enumerate(report.casing_strings)
    ]
    children: list[tuple[type[Base], list[dict[str, Any]]]] = [
        (m.Activity, activities),
        (m.Fluid, _rows(report.fluids, report_id=report_id)),
        (m.SurveyStation, _rows(report.survey_stations, report_id=report_id)),
        (m.PorePressure, _rows(report.pore_pressures, report_id=report_id)),
        (m.LithologyShow, _rows(report.lith_shows, report_id=report_id)),
        (m.StratPick, _rows(report.strat_tops, report_id=report_id)),
        (m.GasReading, _rows(report.gas_readings, report_id=report_id)),
        (m.CasingString, casing),
        (m.EquipmentFailure, _rows(report.equipment_failures, report_id=report_id)),
    ]
    for table, rows in children:
        if rows:
            await session.execute(insert(table), rows)
    return report_id


async def _ingest_files(
    session: AsyncSession,
    files: Sequence[DdrFile],
    wellbore_ids: dict[str, int],
    stats: IngestStats,
) -> None:
    known = set((await session.execute(select(m.SourceFile.sha256))).scalars())
    for file in files:
        stats.files_seen += 1
        if file.sha256 in known:
            stats.files_skipped += 1
            continue
        async with session.begin_nested():
            source_id: int = (
                await session.execute(
                    insert(m.SourceFile)
                    .values(
                        sha256=file.sha256,
                        kind="ddr_xml",
                        source=DDR_MIRROR_DIR,
                        path=file.relative_path,
                        size_bytes=file.size_bytes,
                        parser_version=PARSER_VERSION,
                    )
                    .returning(m.SourceFile.id)
                )
            ).scalar_one()
            for report in file.reports:
                wellbore_id = wellbore_ids[report.wellbore_name]
                clash = await session.scalar(
                    select(m.DailyReport.id).where(
                        m.DailyReport.wellbore_id == wellbore_id,
                        m.DailyReport.start_at == report.start_at,
                    )
                )
                if clash is not None:
                    stats.reports_conflicting.append(file.relative_path)
                    log.warning("report_period_already_loaded", path=file.relative_path)
                    continue
                await _insert_report(session, report, wellbore_id, source_id)
        known.add(file.sha256)
        stats.files_ingested += 1


# ----------------------------------------------------------------------------- derived


async def _survey_stations(session: AsyncSession, wellbore_id: int) -> list[traj.SurveyStation]:
    rows = await session.execute(
        select(
            m.SurveyStation.md_m,
            m.SurveyStation.incl_deg,
            m.SurveyStation.azi_deg,
            m.SurveyStation.tvd_m,
            m.SurveyStation.at,
        )
        .join(m.DailyReport, m.DailyReport.id == m.SurveyStation.report_id)
        .where(m.DailyReport.wellbore_id == wellbore_id)
    )
    return [
        traj.SurveyStation(md_m=md, incl_deg=inc, azi_deg=azi, tvd_reported_m=tvd, measured_at=at)
        for md, inc, azi, tvd, at in rows
        if md is not None and inc is not None and azi is not None
    ]


def compose_trajectory(
    registry: dict[str, WellboreRecord], stations: dict[str, list[traj.SurveyStation]], name: str
) -> list[traj.TrajectoryStation]:
    """Minimum-curvature trajectory for `name`, tied onto its parents at the kick-offs."""
    chain = ancestry(registry, name)
    combined = traj.clean_stations(stations.get(chain[-1].name, []))
    inherited_below = -1.0
    for child in reversed(chain[:-1]):
        kickoff = child.kickoff_md_m if child.kickoff_md_m is not None else 0.0
        combined, cut = traj.compose_with_parent(stations.get(child.name, []), combined, kickoff)
        inherited_below = cut if child.name == name else inherited_below
    computed = traj.minimum_curvature(combined, inherited_below_md_m=inherited_below)
    return traj.reconcile_reported_tvd(computed)


async def _rebuild_trajectories(
    session: AsyncSession,
    registry: dict[str, WellboreRecord],
    wellbore_ids: dict[str, int],
    stats: IngestStats,
) -> dict[str, traj.Trajectory]:
    stations = {name: await _survey_stations(session, wid) for name, wid in wellbore_ids.items()}
    trajectories: dict[str, traj.Trajectory] = {}
    for name, record in sorted(registry.items()):
        wid = wellbore_ids[name]
        computed = compose_trajectory(registry, stations, name)
        trajectories[name] = traj.Trajectory(computed)
        surface = surface_location(record)
        kb = record.kb_elevation_m
        rows = [
            {
                "wellbore_id": wid,
                "seq": i,
                "md_m": s.md_m,
                "tvd_m": s.tvd_m,
                "tvdss_m": s.tvd_m - kb if kb is not None else None,
                "incl_deg": s.incl_deg,
                "azi_deg": s.azi_deg,
                "north_m": s.north_m,
                "east_m": s.east_m,
                "easting_m": surface.easting_m + s.east_m,
                "northing_m": surface.northing_m + s.north_m,
                "dls_deg_per_30m": s.dls_deg_per_30m,
                "tvd_mincurv_m": s.tvd_mincurv_m,
                "tvd_reported_m": s.tvd_reported_m,
                "tvd_source": s.tvd_source.value,
                "reported_tvd_rejected": s.reported_rejected,
                "inherited": s.inherited,
            }
            for i, s in enumerate(computed)
        ]
        await session.execute(
            delete(m.TrajectoryStation).where(m.TrajectoryStation.wellbore_id == wid)
        )
        await session.execute(insert(m.TrajectoryStation), rows)
        stats.trajectory_stations += len(rows)
    return trajectories


def own_tops(
    registry: dict[str, WellboreRecord],
    picks: dict[str, list[tuple[str, float]]],
    sodir_tops: Sequence[SodirLithoTop],
    pack: BasinPack,
) -> tuple[dict[str, list[FormationTop]], dict[str, int]]:
    """Each wellbore's own resolved tops (Sodir + DDR picks) and the unresolved pick names.

    `picks` maps a wellbore to its DDR formation picks as (description, MD top).
    """
    sodir_by_npdid: dict[int, list[SodirLithoTop]] = defaultdict(list)
    for sodir_top in sodir_tops:
        sodir_by_npdid[sodir_top.npdid_wellbore].append(sodir_top)
    unresolved: dict[str, int] = defaultdict(int)
    own: dict[str, list[FormationTop]] = {}
    for name, record in registry.items():
        candidates = [
            resolve_top(pack, desc, md, None, TopSource.DDR) for desc, md in picks.get(name, [])
        ]
        # Sodir tops describe the regulator's hole for this id: the latest technical sidetrack.
        # A wellbore that was redrilled (no Sodir TD recorded for it) gets DDR picks only.
        if record.total_depth_md_m is not None:
            candidates += [
                resolve_top(pack, t.unit_name, t.md_top_m, None, TopSource.SODIR)
                for t in sodir_by_npdid.get(record.location.npdid, [])
            ]
        for candidate in candidates:
            if not candidate.recognised:
                unresolved[candidate.raw_name] += 1
        own[name] = consolidate_tops(candidates)
    return own, dict(sorted(unresolved.items()))


async def _ddr_picks(
    session: AsyncSession, wellbore_ids: dict[str, int]
) -> dict[str, list[tuple[str, float]]]:
    picks: dict[str, list[tuple[str, float]]] = {}
    for name, wid in wellbore_ids.items():
        rows = await session.execute(
            select(m.StratPick.description, m.StratPick.md_top_m)
            .join(m.DailyReport, m.DailyReport.id == m.StratPick.report_id)
            .where(m.DailyReport.wellbore_id == wid)
        )
        picks[name] = [(desc, md) for desc, md in rows.tuples() if desc and md is not None]
    return picks


def final_tops(
    registry: dict[str, WellboreRecord],
    own: dict[str, list[FormationTop]],
    trajectories: dict[str, traj.Trajectory],
) -> dict[str, list[FormationTop]]:
    """Own tops, plus parent tops above each kick-off, plus field correlation where empty."""
    final: dict[str, list[FormationTop]] = {}
    for name in sorted(registry, key=lambda n: (len(ancestry(registry, n)), n)):
        record = registry[name]
        if record.parent_name is None or record.kickoff_md_m is None:
            final[name] = own[name]
        else:
            final[name] = inherit_from_parent(
                own[name], final[record.parent_name], record.kickoff_md_m, record.parent_name
            )
    field_tvdss = field_median_tvdss(
        (top, trajectories[name].tvd_at_md(top.md_top_m) - kb)
        for name, tops in final.items()
        if (kb := registry[name].kb_elevation_m) is not None
        for top in tops
    )
    for name, tops in final.items():
        kb = registry[name].kb_elevation_m
        if not tops and kb is not None:
            final[name] = correlate_tops(field_tvdss, trajectories[name].md_at_tvd, kb)
    return final


async def _rebuild_formation_tops(
    session: AsyncSession,
    bundle: SourceBundle,
    wellbore_ids: dict[str, int],
    trajectories: dict[str, traj.Trajectory],
    *,
    pack: BasinPack,
    stats: IngestStats,
) -> None:
    picks = await _ddr_picks(session, wellbore_ids)
    own, stats.unresolved_formation_names = own_tops(
        bundle.registry, picks, bundle.sodir_tops, pack
    )
    for name, tops in sorted(final_tops(bundle.registry, own, trajectories).items()):
        wid = wellbore_ids[name]
        kb = bundle.registry[name].kb_elevation_m
        rows = []
        for top in tops:
            tvd = trajectories[name].tvd_at_md(top.md_top_m)
            rows.append(
                {
                    "wellbore_id": wid,
                    "basin_pack": pack.key,
                    "name": top.name,
                    "level": top.level.value,
                    "md_top_m": top.md_top_m,
                    "tvd_top_m": tvd,
                    "tvdss_top_m": tvd - kb if kb is not None else None,
                    "source": top.source.value,
                    "raw_name": top.raw_name,
                    "inherited_from_id": (
                        wellbore_ids[top.inherited_from] if top.inherited_from else None
                    ),
                }
            )
        await session.execute(delete(m.FormationTop).where(m.FormationTop.wellbore_id == wid))
        if rows:
            await session.execute(insert(m.FormationTop), rows)
        stats.formation_tops += len(rows)


async def run_ingest(session: AsyncSession, data_dir: Path, basin_pack: str) -> IngestStats:
    """Full, idempotent load. Commits on success; nothing is written on failure."""
    pack = load_basin_pack(basin_pack)
    bundle = read_sources(data_dir)
    stats = IngestStats()
    try:
        well_ids = await _upsert_wells(session, bundle.registry)
        wellbore_ids = await _upsert_wellbores(session, bundle.registry, well_ids)
        stats.wellbores = len(wellbore_ids)
        await _ingest_files(session, bundle.ddr_files, wellbore_ids, stats)
        trajectories = await _rebuild_trajectories(session, bundle.registry, wellbore_ids, stats)
        await _rebuild_formation_tops(
            session, bundle, wellbore_ids, trajectories, pack=pack, stats=stats
        )
    except BaseException:
        await session.rollback()
        raise
    await session.commit()
    log.info(
        "ingest_complete",
        files_ingested=stats.files_ingested,
        files_skipped=stats.files_skipped,
        wellbores=stats.wellbores,
    )
    return stats


async def table_counts(session: AsyncSession) -> dict[str, int]:
    """Row counts of every canonical table (used by the idempotency check)."""
    counts: dict[str, int] = {}
    for table in sorted(Base.metadata.sorted_tables, key=lambda t: t.name):
        counts[table.name] = (
            await session.execute(select(func.count()).select_from(table))
        ).scalar_one()
    return counts


__all__ = [
    "PARSER_VERSION",
    "IngestStats",
    "SourceBundle",
    "compose_trajectory",
    "final_tops",
    "own_tops",
    "read_sources",
    "run_ingest",
    "surface_location",
    "table_counts",
]
