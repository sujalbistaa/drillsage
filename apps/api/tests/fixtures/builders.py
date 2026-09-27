"""Builders for small synthetic WITSML DDRs and Sodir CSV exports.

Nothing here is Volve data: the geometry and names are invented so tests stay independent of
the licensed dataset and can state exact expected values.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

NS = "http://www.witsml.org/schemas/1series"


@dataclass(frozen=True)
class Survey:
    md_m: float
    incl_deg: float
    azi_deg: float
    tvd_m: float | None = None


@dataclass(frozen=True)
class Act:
    hours: float
    md_m: float
    code: str = "drilling -- drill"
    state: str = "ok"
    detail: str = "success"
    comment: str = "Drilled ahead."


@dataclass(frozen=True)
class Day:
    wellbore: str
    npdid: int
    day: date
    report_no: int
    md_m: float
    surveys: Sequence[Survey] = ()
    activities: Sequence[Act] = (Act(24.0, 0.0),)
    strat: Sequence[tuple[float, str]] = ()
    elev_kelly_m: float = 30.0
    md_kickoff_m: float | None = None
    well: str | None = None
    extra_xml: str = ""
    spud: date = field(default=date(2020, 1, 1))


def _t(day: date, hours: float) -> str:
    """ISO timestamp `hours` after midnight UTC of `day`."""
    return (datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(hours=hours)).isoformat()


def ddr_xml(d: Day) -> bytes:
    """One daily report as a WITSML `drillReports` document."""
    start = _t(d.day, 0)
    end = _t(d.day + timedelta(days=1), 0)
    acts = []
    clock = 0.0
    for a in d.activities:
        acts.append(
            f"<activity><dTimStart>{_t(d.day, clock)}</dTimStart>"
            f"<dTimEnd>{_t(d.day, clock + a.hours)}</dTimEnd>"
            f'<md uom="m">{a.md_m}</md><phase>fixed</phase>'
            f"<proprietaryCode>{a.code}</proprietaryCode><state>{a.state}</state>"
            f"<stateDetailActivity>{a.detail}</stateDetailActivity>"
            f"<comments>{a.comment}</comments></activity>"
        )
        clock += a.hours
    surveys = "".join(
        f'<surveyStation><dTim>{end}</dTim><md uom="m">{s.md_m}</md>'
        f'<tvd uom="m">{-999.99 if s.tvd_m is None else s.tvd_m}</tvd>'
        f'<incl uom="dega">{s.incl_deg}</incl><azi uom="dega">{s.azi_deg}</azi></surveyStation>'
        for s in d.surveys
    )
    strat = "".join(
        f'<stratInfo><dTim>{end}</dTim><mdTop uom="m">{md}</mdTop>'
        f'<tvdTop uom="m">-999.99</tvdTop><description>{name}</description></stratInfo>'
        for md, name in d.strat
    )
    kickoff = "" if d.md_kickoff_m is None else f'<mdKickoff uom="m">{d.md_kickoff_m}</mdKickoff>'
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<drillReports xmlns="{NS}" version="1.4.0.0"><drillReport>
<nameWell>NO {d.well or d.wellbore}</nameWell><nameWellbore>NO {d.wellbore}</nameWellbore>
<dTimStart>{start}</dTimStart><dTimEnd>{end}</dTimEnd>
<wellboreAlias><name>{d.wellbore}</name><namingSystem>NPD code</namingSystem></wellboreAlias>
<wellboreAlias><name>{d.npdid}</name><namingSystem>NPD number</namingSystem></wellboreAlias>
<wellboreInfo><dTimSpud>{_t(d.spud, 0)}</dTimSpud><operator>Example Operator</operator>
<rigAlias><name>TEST RIG</name><namingSystem>NPD Name</namingSystem></rigAlias></wellboreInfo>
<statusInfo><reportNo>{d.report_no}</reportNo><dTim>{end}</dTim><md uom="m">{d.md_m}</md>
{kickoff}<elevKelly uom="m">{d.elev_kelly_m}</elevKelly><waterDepth uom="m">80</waterDepth>
<sum24Hr>Day {d.report_no} on {d.wellbore}.</sum24Hr></statusInfo>
{surveys}{"".join(acts)}{strat}{d.extra_xml}
</drillReport></drillReports>"""
    return xml.encode()


SODIR_WELLBORE_HEADER = (
    "wlbWellboreName,wlbWell,wlbNpdidWellbore,wlbDiskosWellboreType,wlbDiskosWellboreParent,"
    "wlbPurpose,wlbStatus,wlbContent,wlbField,wlbDrillingOperator,wlbDrillingFacility,"
    "wlbEntryDate,wlbCompletionDate,wlbKellyBushElevation,wlbWaterDepth,wlbTotalDepth,"
    "wlbFinalVerticalDepth,wlbKickOffPoint,wlbGeodeticDatum,wlbNsDecDeg,wlbEwDecDeg,wlbUtmZone"
)


@dataclass(frozen=True)
class SodirRow:
    name: str
    well: str
    npdid: int
    kind: str = "initial"
    parent: str = ""
    kickoff_md_m: float | None = None
    total_depth_md_m: float = 2000.0
    final_tvd_m: float = 2000.0
    kb_m: float = 30.0
    lat: float = 58.44
    lon: float = 1.89


def sodir_wellbores_csv(rows: Sequence[SodirRow]) -> str:
    lines = [SODIR_WELLBORE_HEADER]
    for r in rows:
        kop = "" if r.kickoff_md_m is None else str(r.kickoff_md_m)
        lines.append(
            f"{r.name},{r.well},{r.npdid},{r.kind},{r.parent},PRODUCTION,P&A,OIL,TESTFIELD,"
            f"Example Operator,TEST RIG,01.01.2020,01.03.2020,{r.kb_m},80.0,"
            f"{r.total_depth_md_m},{r.final_tvd_m},{kop},ED50,{r.lat},{r.lon},31"
        )
    return "﻿" + "\n".join(lines) + "\n"


def sodir_litho_csv(rows: Sequence[tuple[str, int, float, float, str, str]]) -> str:
    """Rows of (wellbore, npdid, top_md, bottom_md, unit name, level)."""
    header = "wlbName,lsuTopDepth,lsuBottomDepth,lsuName,lsuLevel,wlbNpdidWellbore"
    lines = [header] + [f"{w},{t},{b},{n},{lvl},{npd}" for w, npd, t, b, n, lvl in rows]
    return "﻿" + "\n".join(lines) + "\n"


def write_dataset(
    data_dir: Path,
    days: Sequence[Day],
    sodir: Sequence[SodirRow],
    litho: Sequence[tuple[str, int, float, float, str, str]] = (),
) -> None:
    """Lay out `data/raw/` exactly as `drillsage-data fetch` does."""
    reports = data_dir / "raw" / "volve_ddr_mirror" / "Reports"
    reports.mkdir(parents=True, exist_ok=True)
    for d in days:
        stem = d.wellbore.replace("/", "_").replace("-", "_").replace(" ", "_")
        (reports / f"{stem}_{d.day:%Y_%m_%d}.xml").write_bytes(ddr_xml(d))
    sodir_dir = data_dir / "raw" / "sodir"
    sodir_dir.mkdir(parents=True, exist_ok=True)
    (sodir_dir / "wellbore_exploration_all.csv").write_text(
        sodir_wellbores_csv([]), encoding="utf-8"
    )
    (sodir_dir / "wellbore_development_all.csv").write_text(
        sodir_wellbores_csv(sodir), encoding="utf-8"
    )
    (sodir_dir / "strat_litho_wellbore.csv").write_text(sodir_litho_csv(litho), encoding="utf-8")
