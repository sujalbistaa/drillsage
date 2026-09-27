from datetime import UTC, date, datetime

import pytest

from drillsage.ingest.registry import (
    DdrWellboreSummary,
    RegistryError,
    ancestry,
    build_registry,
    mode,
)
from drillsage.ingest.sodir import (
    SodirFormatError,
    SodirWellbore,
    parse_litho_tops,
    parse_wellbores,
)
from tests.fixtures.builders import SodirRow, sodir_litho_csv, sodir_wellbores_csv


def test_parse_wellbores() -> None:
    text = sodir_wellbores_csv(
        [
            SodirRow("9/9-A-1", "9/9-A-1", 100),
            SodirRow("9/9-A-1 A", "9/9-A-1", 101, "sidetrack", "9/9-A-1", kickoff_md_m=1200),
        ]
    )
    rows = parse_wellbores(text, source="dev.csv")
    assert [r.name for r in rows] == ["9/9-A-1", "9/9-A-1 A"]
    side = rows[1]
    assert side.parent_name == "9/9-A-1"
    assert side.kickoff_md_m == 1200
    assert side.entry_on == date(2020, 1, 1)
    assert side.geodetic_datum == "ED50"
    assert rows[0].kickoff_md_m is None


def test_parse_wellbores_skips_rows_without_coordinates_and_checks_columns() -> None:
    text = sodir_wellbores_csv([SodirRow("9/9-A-1", "9/9-A-1", 100)]).replace(",58.44,1.89,", ",,,")
    assert parse_wellbores(text, source="x") == []
    with pytest.raises(SodirFormatError, match="missing columns"):
        parse_wellbores("a,b\n1,2\n", source="x")


def test_parse_litho_tops_filters_by_npdid() -> None:
    text = sodir_litho_csv(
        [
            ("9/9-A-1", 100, 850, 1100, "UTSIRA FM", "FORMATION"),
            ("9/9-B-1", 200, 900, 1000, "UTSIRA FM", "FORMATION"),
        ]
    )
    tops = parse_litho_tops(text, source="x", npdids=[100])
    assert len(tops) == 1
    assert (tops[0].unit_name, tops[0].level, tops[0].md_top_m) == ("UTSIRA FM", "formation", 850)


def _summary(name: str, npdid: int | None, **kw: object) -> DdrWellboreSummary:
    base: dict[str, object] = {
        "name": name,
        "npdid": npdid,
        "spud_at": datetime(2020, 1, 1, tzinfo=UTC),
        "drill_complete_on": None,
        "first_report_at": datetime(2020, 1, 1, tzinfo=UTC),
        "last_report_at": datetime(2020, 2, 1, tzinfo=UTC),
        "kickoff_md_m": None,
        "first_survey_md_m": 100.0,
        "operator": "Op",
        "rig_name": "Rig",
        "elev_kelly_m": 30.0,
        "water_depth_m": 80.0,
    }
    base.update(kw)
    return DdrWellboreSummary(**base)  # type: ignore[arg-type]


def _sodir(*rows: SodirRow) -> list[SodirWellbore]:
    return parse_wellbores(sodir_wellbores_csv(rows), source="x")


def test_registry_links_sidetracks_and_technical_sidetracks() -> None:
    ddr = {
        "9/9-A-1": _summary("9/9-A-1", 100),
        "9/9-A-1 T2": _summary("9/9-A-1 T2", 100, kickoff_md_m=600.0),
        "9/9-A-1 A": _summary("9/9-A-1 A", 101),
    }
    sodir = _sodir(
        SodirRow("9/9-A-1", "9/9-A-1", 100, total_depth_md_m=3000),
        SodirRow("9/9-A-1 A", "9/9-A-1", 101, "sidetrack", "9/9-A-1", kickoff_md_m=1500),
    )
    registry = build_registry(ddr, sodir)

    t2 = registry["9/9-A-1 T2"]
    assert (t2.kind, t2.parent_name, t2.kickoff_md_m) == ("technical_sidetrack", "9/9-A-1", 600)
    # Sodir's parent was redrilled as T2, so the sidetrack leaves the T2 hole.
    side = registry["9/9-A-1 A"]
    assert (side.kind, side.parent_name, side.kickoff_md_m) == ("sidetrack", "9/9-A-1 T2", 1500)
    # The redrilled original does not claim Sodir's final depths (they describe T2).
    assert registry["9/9-A-1"].total_depth_md_m is None
    assert t2.total_depth_md_m == 3000
    assert [r.name for r in ancestry(registry, "9/9-A-1 A")] == [
        "9/9-A-1 A",
        "9/9-A-1 T2",
        "9/9-A-1",
    ]


def test_registry_errors() -> None:
    with pytest.raises(RegistryError, match="no Sodir wellbore"):
        build_registry({"9/9-Z-1": _summary("9/9-Z-1", 999)}, [])
    orphan = _sodir(SodirRow("9/9-A-1 A", "9/9-A-1", 101, "sidetrack", "9/9-A-1", kickoff_md_m=10))
    with pytest.raises(RegistryError, match="has no daily reports"):
        build_registry({"9/9-A-1 A": _summary("9/9-A-1 A", 101)}, orphan)


def test_mode() -> None:
    assert mode([None, 1, 2, 2]) == 2
    assert mode([None, None]) is None
