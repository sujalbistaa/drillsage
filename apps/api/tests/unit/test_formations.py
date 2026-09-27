import pytest

from drillsage.core.basin_packs import available_basin_packs, load_basin_pack
from drillsage.domain.formations import (
    BasinPack,
    FormationTop,
    StratLevel,
    StratUnit,
    TopSource,
    consolidate_tops,
    correlate_tops,
    field_median_tvdss,
    inherit_from_parent,
    name_key,
    resolve_top,
    unit_at_md,
)
from drillsage.domain.names import canonical_wellbore_name, technical_sidetrack

NORTH_SEA = load_basin_pack("north_sea")


@pytest.mark.parametrize(
    ("raw", "key"),
    [
        ("Balder Fm .", "BALDER FM"),
        ("BALDER FORMATION", "BALDER FM"),
        ("Hordaland  Group", "HORDALAND GP"),
        ("Blodøks Fm", "BLODØKS FM"),
        ("Heather Fm.", "HEATHER FM"),
    ],
)
def test_name_key(raw: str, key: str) -> None:
    assert name_key(raw) == key


@pytest.mark.parametrize(
    ("raw", "unit"),
    [
        ("BALDER FM", "Balder Fm"),
        ("Skagerak Fm", "Skagerrak Fm"),
        ("RØDBY FM", "Rødby Fm"),
        ("NO FORMAL NAME", "Hordaland Gp undifferentiated"),
        ("Hordaland Gp", "Hordaland Gp"),
    ],
)
def test_north_sea_pack_resolves_sodir_and_ddr_spellings(raw: str, unit: str) -> None:
    resolved = NORTH_SEA.resolve(raw)
    assert resolved is not None
    assert resolved.name == unit


def test_norwegian_sea_names_are_not_north_sea_units() -> None:
    for name in ("Kai Fm", "Brygge Fm", "Lysing Fm", "Springar Fm"):
        assert NORTH_SEA.resolve(name) is None


def test_both_packs_load_and_order_units() -> None:
    assert available_basin_packs() == ["assam_arakan", "north_sea"]
    assam = load_basin_pack("assam_arakan")
    names = [u.name for u in assam.units]
    assert names.index("Tipam Gp") < names.index("Barail Gp") < names.index("Kopili Fm")
    girujan = assam.resolve("Girujan Clay")
    assert girujan is not None
    assert assam.order(girujan) < assam.order(assam.units[-1])
    with pytest.raises(KeyError):
        load_basin_pack("atlantis")


def test_ambiguous_pack_is_rejected() -> None:
    with pytest.raises(ValueError, match="ambiguous"):
        BasinPack(
            key="bad",
            name="bad",
            units=(
                StratUnit("A Fm", StratLevel.FORMATION, aliases=("X",)),
                StratUnit("B Fm", StratLevel.FORMATION, aliases=("X",)),
            ),
        )


def top(
    name: str,
    md: float,
    source: TopSource = TopSource.DDR,
    level: StratLevel = StratLevel.FORMATION,
    inherited_from: str | None = None,
) -> FormationTop:
    return FormationTop(
        name=name,
        level=level,
        md_top_m=md,
        tvd_top_m=None,
        source=source,
        recognised=True,
        raw_name=name,
        inherited_from=inherited_from,
    )


def test_resolve_top_flags_unknown_names() -> None:
    known = resolve_top(NORTH_SEA, "Balder Fm .", 2961, None, TopSource.DDR)
    assert known.recognised
    assert known.name == "Balder Fm"
    unknown = resolve_top(NORTH_SEA, "Kai Fm", 1561.5, None, TopSource.DDR)
    assert not unknown.recognised
    assert unknown.level is StratLevel.FORMATION
    group = resolve_top(NORTH_SEA, "NO GROUP DEFINED", 10, None, TopSource.SODIR)
    assert not group.recognised


def test_consolidate_prefers_sodir_then_shallowest_pick() -> None:
    tops = consolidate_tops(
        [
            top("Balder Fm", 2975),
            top("Balder Fm", 2961),
            top("Sele Fm", 3025, TopSource.DDR),
            top("Sele Fm", 3021, TopSource.SODIR),
            top("Hordaland Gp", 1111, level=StratLevel.GROUP),
            resolve_top(NORTH_SEA, "Kai Fm", 1500, None, TopSource.DDR),
        ]
    )
    assert [(t.name, t.md_top_m, t.source) for t in tops] == [
        ("Hordaland Gp", 1111, TopSource.DDR),
        ("Balder Fm", 2961, TopSource.DDR),
        ("Sele Fm", 3021, TopSource.SODIR),
    ]


def test_sidetrack_inherits_parent_tops_above_kickoff() -> None:
    parent = [top("Utsira Fm", 850), top("Balder Fm", 2300), top("Hugin Fm", 3100)]
    own = [top("Balder Fm", 2610), top("Hugin Fm", 3250)]  # "formation at kick-off" pick
    tops = inherit_from_parent(own, parent, kickoff_md_m=2600, parent_name="P")
    by_name = {t.name: t for t in tops}
    assert by_name["Utsira Fm"].inherited_from == "P"
    assert by_name["Balder Fm"].md_top_m == 2300
    assert by_name["Balder Fm"].inherited_from == "P"
    assert by_name["Hugin Fm"].md_top_m == 3250
    assert by_name["Hugin Fm"].inherited_from is None


def test_field_correlation_uses_median_and_needs_support() -> None:
    samples = [
        (top("Utsira Fm", 0), 800.0),
        (top("Utsira Fm", 0), 820.0),
        (top("Utsira Fm", 0), 900.0),
        (top("Balder Fm", 0), 2200.0),
        (top("Balder Fm", 0), 2210.0),  # only two wells: not enough support
        (top("Utsira Fm", 0, inherited_from="P"), 5000.0),  # inherited: excluded
    ]
    medians = field_median_tvdss(samples)
    assert medians == {("Utsira Fm", StratLevel.FORMATION): 820.0}

    tops = correlate_tops(medians, lambda tvd: tvd + 5.0 if tvd < 1000 else None, 30.0)
    assert len(tops) == 1
    assert tops[0].source is TopSource.CORRELATED
    assert tops[0].tvd_top_m == 850.0
    assert tops[0].md_top_m == 855.0
    assert correlate_tops(medians, lambda _tvd: None, 30.0) == []


def test_unit_at_md() -> None:
    tops = [
        top("Utsira Fm", 850),
        top("Balder Fm", 2300),
        top("Hordaland Gp", 1100, level=StratLevel.GROUP),
    ]
    assert unit_at_md(tops, 500) is None
    at_1000 = unit_at_md(tops, 1000)
    assert at_1000 is not None
    assert at_1000.name == "Utsira Fm"
    at_2400 = unit_at_md(tops, 2400)
    assert at_2400 is not None
    assert at_2400.name == "Balder Fm"
    group = unit_at_md(tops, 2400, StratLevel.GROUP)
    assert group is not None
    assert group.name == "Hordaland Gp"


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("NO 15/9-F-1 C", "15/9-F-1 C"),
        ("  NO   15/9-19  BT2 ", "15/9-19 BT2"),
        ("15/9-F-4", "15/9-F-4"),
    ],
)
def test_canonical_wellbore_name(raw: str, canonical: str) -> None:
    assert canonical_wellbore_name(raw) == canonical


def test_technical_sidetrack_parsing() -> None:
    bt2 = technical_sidetrack("NO 15/9-19 BT2")
    assert bt2 is not None
    assert (bt2.base, bt2.number) == ("15/9-19 B", 2)
    t2 = technical_sidetrack("15/9-F-11 T2")
    assert t2 is not None
    assert (t2.base, t2.number) == ("15/9-F-11", 2)
    assert technical_sidetrack("15/9-F-1 C") is None
    assert technical_sidetrack("15/9-T2") is None
