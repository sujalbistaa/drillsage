"""Reconcile wellbores named in daily reports with the regulator's (Sodir) wellbore register.

Rules, all driven by real Volve quirks:

1. The join key is the DDR's `NPD number` alias = Sodir `wlbNpdidWellbore`.
2. Technical sidetracks (`15/9-19 BT2`, `15/9-F-11 T2`) share their parent's regulator id and
   have no Sodir row of their own. Their parent is the base name; their kick-off comes from
   the DDR `mdKickoff`, else their first survey.
3. When Sodir names a parent that was later technically sidetracked, the hole that physically
   exists is the latest technical sidetrack, so child sidetracks tie onto that instead
   (`15/9-F-11 A` leaves the hole drilled as `15/9-F-11 T2`).
4. Coordinates, kelly-bushing elevation and water depth come from Sodir; the surface location
   of a well is shared by all its wellbores.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime

from drillsage.domain.names import technical_sidetrack
from drillsage.ingest.sodir import SodirWellbore


@dataclass(frozen=True, slots=True)
class DdrWellboreSummary:
    """What the daily reports say about one wellbore, aggregated over its reports."""

    name: str
    npdid: int | None
    spud_at: datetime | None
    drill_complete_on: date | None
    first_report_at: datetime
    last_report_at: datetime
    kickoff_md_m: float | None
    first_survey_md_m: float | None
    operator: str | None
    rig_name: str | None
    elev_kelly_m: float | None
    water_depth_m: float | None


@dataclass(frozen=True, slots=True)
class WellboreRecord:
    name: str
    well_name: str
    npdid: int | None
    kind: str
    parent_name: str | None
    kickoff_md_m: float | None
    purpose: str | None
    content: str | None
    operator: str | None
    rig_name: str | None
    kb_elevation_m: float | None
    water_depth_m: float | None
    total_depth_md_m: float | None
    final_tvd_m: float | None
    spud_at: datetime | None
    completed_on: date | None
    first_report_at: datetime
    last_report_at: datetime
    location: SodirWellbore


class RegistryError(ValueError):
    pass


def mode[T](values: Iterable[T | None]) -> T | None:
    """Most common non-null value (first seen wins ties); None when there are none."""
    counts = Counter(v for v in values if v is not None)
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def _latest_technical_sidetrack(name: str, names: Iterable[str]) -> str:
    best, best_n = name, 0
    for candidate in names:
        ts = technical_sidetrack(candidate)
        if ts is not None and ts.base == name and ts.number > best_n:
            best, best_n = candidate, ts.number
    return best


def build_registry(
    ddr: Mapping[str, DdrWellboreSummary], sodir: Iterable[SodirWellbore]
) -> dict[str, WellboreRecord]:
    by_npdid: dict[int, SodirWellbore] = {}
    by_name: dict[str, SodirWellbore] = {}
    for record in sodir:
        by_npdid[record.npdid] = record
        by_name[record.name] = record

    records: dict[str, WellboreRecord] = {}
    for name, summary in sorted(ddr.items()):
        ts = technical_sidetrack(name)
        location = (by_npdid.get(summary.npdid) if summary.npdid is not None else None) or (
            by_name.get(ts.base if ts else name)
        )
        if location is None:
            raise RegistryError(f"{name}: no Sodir wellbore for NPD id {summary.npdid}")

        if ts is not None:
            kind = "technical_sidetrack"
            parent: str | None = ts.base
            kickoff = summary.kickoff_md_m or summary.first_survey_md_m
            purpose = location.purpose
        else:
            kind = location.wellbore_type or "initial"
            parent = location.parent_name
            kickoff = location.kickoff_md_m
            purpose = location.purpose
            if parent is not None:
                parent = _latest_technical_sidetrack(parent, ddr.keys())

        if parent is not None and parent not in ddr:
            raise RegistryError(f"{name}: parent wellbore {parent} has no daily reports")

        records[name] = WellboreRecord(
            name=name,
            well_name=location.well_name,
            npdid=summary.npdid,
            kind=kind,
            parent_name=parent,
            kickoff_md_m=kickoff if parent is not None else None,
            purpose=purpose.lower() if purpose else None,
            content=location.content,
            operator=summary.operator or location.operator,
            rig_name=summary.rig_name or location.drilling_facility,
            kb_elevation_m=location.kb_elevation_m or summary.elev_kelly_m,
            water_depth_m=location.water_depth_m or summary.water_depth_m,
            # Sodir depths describe the final hole under a shared id, which for a wellbore
            # that was later technically sidetracked is the sidetrack, not this hole.
            total_depth_md_m=None
            if _was_redrilled(name, ddr.keys())
            else location.total_depth_md_m,
            final_tvd_m=None if _was_redrilled(name, ddr.keys()) else location.final_tvd_m,
            spud_at=summary.spud_at if ts is None else summary.first_report_at,
            completed_on=summary.drill_complete_on or summary.last_report_at.date(),
            first_report_at=summary.first_report_at,
            last_report_at=summary.last_report_at,
            location=location,
        )
    _check_acyclic(records)
    return records


def _was_redrilled(name: str, names: Iterable[str]) -> bool:
    return _latest_technical_sidetrack(name, names) != name


def _check_acyclic(records: Mapping[str, WellboreRecord]) -> None:
    for start in records:
        seen = {start}
        current = records[start].parent_name
        while current is not None:
            if current in seen:
                raise RegistryError(f"parent cycle through {current}")
            seen.add(current)
            current = records[current].parent_name


def ancestry(records: Mapping[str, WellboreRecord], name: str) -> list[WellboreRecord]:
    """The wellbore followed by its parents, nearest first."""
    chain = [records[name]]
    while (parent := chain[-1].parent_name) is not None:
        chain.append(records[parent])
    return chain
