"""Sodir FactPages CSV exports (Norwegian Offshore Directorate, NLOD licence).

- `wellbore_exploration_all.csv` / `wellbore_development_all.csv`: one row per wellbore with
  surface coordinates (ED50), kelly bushing elevation, kick-off point and parent wellbore.
- `strat_litho_wellbore.csv`: interpreted lithostratigraphic tops (MD from RKB).
"""

import csv
import io
from collections.abc import Iterable, Iterator
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from drillsage.core.errors import InvalidInputError
from drillsage.domain.names import canonical_wellbore_name

_WELLBORE_COLUMNS = frozenset(
    {
        "wlbWellboreName",
        "wlbWell",
        "wlbNpdidWellbore",
        "wlbDiskosWellboreType",
        "wlbDiskosWellboreParent",
        "wlbPurpose",
        "wlbStatus",
        "wlbContent",
        "wlbField",
        "wlbDrillingOperator",
        "wlbDrillingFacility",
        "wlbEntryDate",
        "wlbCompletionDate",
        "wlbKellyBushElevation",
        "wlbWaterDepth",
        "wlbTotalDepth",
        "wlbFinalVerticalDepth",
        "wlbKickOffPoint",
        "wlbGeodeticDatum",
        "wlbNsDecDeg",
        "wlbEwDecDeg",
        "wlbUtmZone",
    }
)
_LITHO_COLUMNS = frozenset(
    {"wlbName", "wlbNpdidWellbore", "lsuTopDepth", "lsuBottomDepth", "lsuName", "lsuLevel"}
)


class SodirFormatError(InvalidInputError):
    slug = "sodir-format"


class SodirWellbore(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    well_name: str
    npdid: int
    wellbore_type: str | None
    """`initial`, `sidetrack` or `re-entry`."""
    parent_name: str | None
    purpose: str | None
    status: str | None
    content: str | None
    field: str | None
    operator: str | None
    drilling_facility: str | None
    entry_on: date | None
    completion_on: date | None
    kb_elevation_m: float | None
    water_depth_m: float | None
    total_depth_md_m: float | None
    final_tvd_m: float | None
    kickoff_md_m: float | None
    geodetic_datum: str
    lat_deg: float
    lon_deg: float
    utm_zone: int | None


class SodirLithoTop(BaseModel):
    model_config = ConfigDict(frozen=True)

    wellbore_name: str
    npdid_wellbore: int
    md_top_m: float
    md_bottom_m: float | None
    unit_name: str
    level: str


def _rows(text: str, required: frozenset[str], source: str) -> Iterator[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text.removeprefix("﻿")))
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise SodirFormatError(f"{source}: missing columns {sorted(missing)}")
    yield from reader


def _text(value: str) -> str | None:
    value = value.strip()
    return value or None


def _float(value: str) -> float | None:
    value = value.strip()
    return float(value) if value else None


def _date(value: str) -> date | None:
    value = value.strip()
    return datetime.strptime(value, "%d.%m.%Y").date() if value else None  # noqa: DTZ007


def parse_wellbores(text: str, *, source: str) -> list[SodirWellbore]:
    wellbores: list[SodirWellbore] = []
    for row in _rows(text, _WELLBORE_COLUMNS, source):
        lat, lon = _float(row["wlbNsDecDeg"]), _float(row["wlbEwDecDeg"])
        if lat is None or lon is None:
            continue
        zone = _text(row["wlbUtmZone"])
        parent = _text(row["wlbDiskosWellboreParent"])
        wellbores.append(
            SodirWellbore(
                name=canonical_wellbore_name(row["wlbWellboreName"]),
                well_name=canonical_wellbore_name(row["wlbWell"]),
                npdid=int(row["wlbNpdidWellbore"]),
                wellbore_type=_text(row["wlbDiskosWellboreType"]),
                parent_name=canonical_wellbore_name(parent) if parent else None,
                purpose=_text(row["wlbPurpose"]),
                status=_text(row["wlbStatus"]),
                content=_text(row["wlbContent"]),
                field=_text(row["wlbField"]),
                operator=_text(row["wlbDrillingOperator"]),
                drilling_facility=_text(row["wlbDrillingFacility"]),
                entry_on=_date(row["wlbEntryDate"]),
                completion_on=_date(row["wlbCompletionDate"]),
                kb_elevation_m=_float(row["wlbKellyBushElevation"]),
                water_depth_m=_float(row["wlbWaterDepth"]),
                total_depth_md_m=_float(row["wlbTotalDepth"]),
                final_tvd_m=_float(row["wlbFinalVerticalDepth"]),
                kickoff_md_m=_float(row["wlbKickOffPoint"]),
                geodetic_datum=row["wlbGeodeticDatum"].strip() or "ED50",
                lat_deg=lat,
                lon_deg=lon,
                utm_zone=int(zone) if zone else None,
            )
        )
    return wellbores


def parse_litho_tops(text: str, *, source: str, npdids: Iterable[int]) -> list[SodirLithoTop]:
    """Lithostratigraphic tops for the given wellbores only (the national file is large)."""
    wanted = set(npdids)
    tops: list[SodirLithoTop] = []
    for row in _rows(text, _LITHO_COLUMNS, source):
        npdid = int(row["wlbNpdidWellbore"])
        if npdid not in wanted:
            continue
        top = _float(row["lsuTopDepth"])
        if top is None:
            continue
        tops.append(
            SodirLithoTop(
                wellbore_name=canonical_wellbore_name(row["wlbName"]),
                npdid_wellbore=npdid,
                md_top_m=top,
                md_bottom_m=_float(row["lsuBottomDepth"]),
                unit_name=row["lsuName"].strip(),
                level=row["lsuLevel"].strip().lower(),
            )
        )
    return tops
