"""WITSML DDR parser: golden file, unit normalisation, nulls, format drift and failure modes.

Regenerate the golden file after an intended parser change with
`UPDATE_GOLDEN=1 uv run pytest tests/unit/test_witsml_ddr.py`, then review the diff.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Annotated

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel

from drillsage.core.units import Kind, UnitError
from drillsage.ingest.witsml_ddr import looks_like_ddr, parse_ddr
from drillsage.ingest.xml_safe import parse_xml
from drillsage.ingest.xmlmap import (
    Xml,
    XmlValueError,
    model_value_counts,
    source_leaf_counts,
    spec_for,
)
from tests.fixtures.builders import NS

FIXTURE = Path(__file__).parents[1] / "fixtures" / "ddr" / "synthetic_full.xml"
GOLDEN = Path(__file__).parents[1] / "golden" / "ddr_synthetic_full.json"


def _wrap(body: str, version: str = "1.4.0.0") -> bytes:
    return (
        f'<drillReports xmlns="{NS}" version="{version}"><drillReport>'
        "<nameWellbore>NO 1/2-3</nameWellbore>"
        "<dTimStart>2020-01-01T00:00:00+00:00</dTimStart>"
        "<dTimEnd>2020-01-02T00:00:00+00:00</dTimEnd>"
        f"{body}</drillReport></drillReports>"
    ).encode()


def test_golden_file() -> None:
    parsed = parse_ddr(FIXTURE.read_bytes())
    actual = parsed.document.model_dump(mode="json")
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.write_text(json.dumps(actual, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    assert actual == json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_fidelity_every_leaf_is_mapped_and_counted() -> None:
    data = FIXTURE.read_bytes()
    parsed = parse_ddr(data)
    source, nulls = source_leaf_counts(parse_xml(data))
    assert parsed.report.unmapped == {}
    assert parsed.report.mapped == source
    assert parsed.report.nulls == nulls
    assert sum(nulls.values()) == 7
    values = model_value_counts(parsed.document, "/drillReports")
    assert values == source - nulls


def test_units_are_normalised_to_canonical() -> None:
    report = parse_ddr(FIXTURE.read_bytes()).document.reports[0]
    status = report.status
    assert status is not None
    assert status.md_m == pytest.approx(3048.0)  # 10000 ft
    assert status.hole_diameter_m == pytest.approx(0.31115)  # 12.25 in
    assert status.strength_form_gcc == pytest.approx(14.5 / 8.345404452)  # ppg
    assert status.avg_temp_bh_degc == pytest.approx(100.0)  # 212 degF
    assert status.md_planned_m is None  # -999.99
    assert report.fluids[0].pres_bop_rating_kpa == pytest.approx(69_000)  # 690 bar
    assert report.equipment_failures[0].missed_production_h == pytest.approx(1.5)
    assert report.bit_records[0].nozzles[0].diameter_m == pytest.approx(0.0127)  # 16/32 in


def test_identity_and_derived_values() -> None:
    parsed = parse_ddr(FIXTURE.read_bytes())
    report = parsed.document.reports[0]
    assert parsed.witsml_version == "1.4.0.0"
    assert report.wellbore_name == "99/9-X-1 A"
    assert report.npdid_wellbore == 9001
    assert [a.duration_h for a in report.activities] == [10.5, 2.5]
    assert looks_like_ddr(FIXTURE.read_bytes()[:2048])
    assert not looks_like_ddr(b"<logs/>")


def test_unknown_elements_are_counted_not_dropped() -> None:
    parsed = parse_ddr(_wrap("<futureThing><depth uom='m'>5</depth></futureThing>"))
    assert parsed.report.unmapped == {"/drillReports/drillReport/futureThing/depth": 1}


def test_wellbore_name_falls_back_to_name_wellbore_and_errors_without_one() -> None:
    report = parse_ddr(_wrap("")).document.reports[0]
    assert report.wellbore_name == "1/2-3"
    assert report.npdid_wellbore is None
    nameless = (
        f'<drillReports xmlns="{NS}"><drillReport><name>x</name></drillReport></drillReports>'
    )
    unnamed = parse_ddr(nameless.encode()).document.reports[0]
    with pytest.raises(XmlValueError, match="no wellbore name"):
        _ = unnamed.wellbore_name


@pytest.mark.parametrize(
    ("body", "error", "match"),
    [
        ("<statusInfo><md uom='furlong'>1</md></statusInfo>", UnitError, "furlong"),
        ("<statusInfo><md>1</md></statusInfo>", UnitError, "missing unit"),
        ("<statusInfo><reportNo>7.5</reportNo></statusInfo>", XmlValueError, "integer"),
        ("<statusInfo><reportNo>seven</reportNo></statusInfo>", XmlValueError, "cannot read"),
        ("<statusInfo><hpht>maybe</hpht></statusInfo>", XmlValueError, "cannot read"),
        ("<statusInfo><dTim>2020-01-01T00:00:00</dTim></statusInfo>", XmlValueError, "cannot"),
        ("<fluid><md datum='MSL' uom='m'>1</md></fluid>", XmlValueError, "datum"),
        (
            "<statusInfo><md uom='m'>1</md><md uom='m'>2</md></statusInfo>",
            XmlValueError,
            "repeated",
        ),
        ("<statusInfo/><statusInfo/>", XmlValueError, "repeated"),
    ],
)
def test_bad_values_fail_loudly(body: str, error: type[Exception], match: str) -> None:
    with pytest.raises(error, match=match):
        parse_ddr(_wrap(body))


def test_document_level_validation() -> None:
    with pytest.raises(XmlValueError, match="expected a drillReports"):
        parse_ddr(f'<logs xmlns="{NS}"/>'.encode())
    with pytest.raises(XmlValueError, match="namespace"):
        parse_ddr(b'<drillReports xmlns="urn:other"><drillReport/></drillReports>')
    with pytest.raises(XmlValueError, match="no drillReport"):
        parse_ddr(f'<drillReports xmlns="{NS}"/>'.encode())


@given(
    st.floats(min_value=0, max_value=20_000, allow_nan=False),
    st.sampled_from([("m", 1.0), ("ft", 0.3048), ("in", 0.0254)]),
)
def test_depth_values_round_trip(value: float, unit: tuple[str, float]) -> None:
    uom, factor = unit
    text = repr(value)
    report = parse_ddr(_wrap(f"<statusInfo><md uom='{uom}'>{text}</md></statusInfo>"))
    status = report.document.reports[0].status
    assert status is not None
    assert status.md_m == pytest.approx(float(text) * factor)


class _NoMark(BaseModel):
    depth_m: float | None = None


class _Twice(BaseModel):
    a: Annotated[str | None, Xml("x")] = None
    b: Annotated[str | None, Xml("x")] = None


class _Unitless(BaseModel):
    depth_m: Annotated[float | None, Xml("depth")] = None


class _BadList(BaseModel):
    items: Annotated[list[str], Xml("item")] = []


class _BadType(BaseModel):
    when: Annotated[dict[str, str] | None, Xml("when")] = None


class _Ok(BaseModel):
    when: Annotated[datetime | None, Xml("when")] = None
    depth_m: Annotated[float | None, Xml("depth", Kind.LENGTH)] = None


@pytest.mark.parametrize(
    ("model", "match"),
    [
        (_NoMark, "exactly one Xml"),
        (_Twice, "mapped twice"),
        (_Unitless, "must declare a unit"),
        (_BadList, "lists must hold models"),
        (_BadType, "unsupported annotation"),
    ],
)
def test_mapping_mistakes_are_caught_at_definition(model: type[BaseModel], match: str) -> None:
    with pytest.raises(TypeError, match=match):
        spec_for(model)


def test_valid_spec() -> None:
    spec = spec_for(_Ok)
    assert set(spec.leaves) == {"when", "depth"}
    assert spec.children == {}
