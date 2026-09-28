"""End-to-end ingest against a throwaway Postgres database.

A synthetic field (never Volve data) exercises every pipeline rule: a sidetrack tied onto its
parent, a reported-TVD typo, a duplicate report for an already-loaded day, a formation name
from another basin, and a well with no picks that needs field-correlated tops. The load runs
twice to prove idempotency. The developer's own database is never touched.
"""

import math
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import PostgresDsn
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from drillsage.core.config import Environment, Settings
from drillsage.db import models as m
from drillsage.db.session import Database
from drillsage.extract import report as extraction_report
from drillsage.extract.pipeline import run_extraction
from drillsage.ingest import reports
from drillsage.ingest.cli import main as cli_main
from drillsage.ingest.pipeline import run_ingest, table_counts
from tests.fixtures.builders import Act, Day, SodirRow, Survey, write_dataset

pytestmark = pytest.mark.integration

API_DIR = Path(__file__).resolve().parents[2]
COS30 = math.cos(math.radians(30))


def _slant_surveys(start: float, stop: float, *, typo_at: float | None = None) -> list[Survey]:
    """Vertical to 500 m, then a straight 30° hole: exact reported TVDs except one typo."""
    out = []
    md = start
    while md <= stop:
        if md <= 500:
            out.append(Survey(md, 0.0, 0.0, md))
        else:
            tvd = 500 + (md - 500) * COS30 if md > 500 else md
            out.append(Survey(md, 30.0, 90.0, 24.8 if md == typo_at else round(tvd, 3)))
        md += 100
    return out


def synthetic_field(data_dir: Path) -> None:
    days = [
        Day(
            "9/9-A-1",
            100,
            date(2020, 1, 1),
            1,
            500,
            surveys=_slant_surveys(100, 500),
            strat=[(300.0, "Utsira Fm")],
        ),
        Day(
            "9/9-A-1",
            100,
            date(2020, 1, 2),
            2,
            1500,
            surveys=[Survey(500, 0, 0, 500), *_slant_surveys(600, 1500, typo_at=1100)],
            activities=[
                Act(20, 1400),
                Act(
                    4,
                    1450,
                    "interruption -- lost circulation",
                    "fail",
                    "circulation loss",
                    "Losses 10 m3/h at 1450 m.",
                ),
            ],
            strat=[(1400.0, "Balder Fm ."), (900.0, "Kai Fm")],
        ),
        Day(
            "9/9-A-1 A",
            101,
            date(2020, 1, 5),
            1,
            1800,
            md_kickoff_m=1000,
            surveys=[
                Survey(1100, 40.0, 90.0, None),
                Survey(1400, 45.0, 90.0, None),
                Survey(1800, 50.0, 90.0, None),
            ],
            strat=[(1450.0, "Balder Fm")],
        ),
        Day(
            "9/9-C-1",
            300,
            date(2019, 6, 1),
            1,
            800,
            surveys=_slant_surveys(100, 800),
            strat=[(320.0, "Utsira Fm")],
        ),
        Day(
            "9/9-D-1",
            400,
            date(2019, 7, 1),
            1,
            800,
            surveys=_slant_surveys(100, 800),
            strat=[(310.0, "Utsira Fm")],
        ),
        Day("9/9-B-1", 200, date(2019, 8, 1), 1, 800, surveys=_slant_surveys(100, 800)),
    ]
    sodir = [
        SodirRow("9/9-A-1", "9/9-A-1", 100, total_depth_md_m=1500, final_tvd_m=500 + 1000 * COS30),
        SodirRow(
            "9/9-A-1 A",
            "9/9-A-1",
            101,
            "sidetrack",
            "9/9-A-1",
            kickoff_md_m=1000,
            total_depth_md_m=1800,
            final_tvd_m=1400,
        ),
        SodirRow("9/9-B-1", "9/9-B-1", 200, lat=58.45, lon=1.90),
        SodirRow("9/9-C-1", "9/9-C-1", 300, lat=58.46, lon=1.91),
        SodirRow("9/9-D-1", "9/9-D-1", 400, lat=58.47, lon=1.92),
    ]
    write_dataset(data_dir, days, sodir)
    # A second copy of A-1's first day with different content: same wellbore and period.
    duplicate = data_dir / "raw" / "volve_ddr_mirror" / "Reports" / "9_9_A_1_dup.xml"
    original = next(
        (data_dir / "raw" / "volve_ddr_mirror" / "Reports").glob("9_9_A_1_2020_01_01.xml")
    )
    duplicate.write_bytes(original.read_bytes().replace(b"Day 1 on", b"Resubmitted day 1 on"))


@pytest.fixture(scope="module")
async def test_db_url() -> AsyncIterator[str]:
    base = make_url(str(Settings(environment=Environment.TEST).database_url))
    name = f"drillsage_test_{uuid.uuid4().hex[:8]}"
    admin = create_async_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception:
        await admin.dispose()
        pytest.skip("Postgres not reachable; run `make db-up`")
    yield base.set(database=name).render_as_string(hide_password=False)
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    await admin.dispose()


@pytest.fixture(scope="module")
def migrated_url(test_db_url: str) -> Iterator[str]:
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", test_db_url)
    command.upgrade(config, "head")
    yield test_db_url
    command.downgrade(config, "base")


@pytest.fixture(scope="module")
async def session(migrated_url: str) -> AsyncIterator[AsyncSession]:
    database = Database(
        Settings(environment=Environment.TEST, database_url=PostgresDsn(migrated_url))
    )
    async for s in database.session():
        yield s
    await database.dispose()


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("data")
    synthetic_field(root)
    return root


async def test_ingest_is_idempotent_and_applies_every_rule(
    session: AsyncSession, data_dir: Path, tmp_path: Path
) -> None:
    first = await run_ingest(session, data_dir, "north_sea")
    counts = await table_counts(session)
    assert first.files_seen == 7
    assert first.files_ingested == 7
    assert first.reports_conflicting == ["raw/volve_ddr_mirror/Reports/9_9_A_1_dup.xml"]
    assert first.unresolved_formation_names == {"Kai Fm": 1}
    assert counts["daily_reports"] == 6
    assert counts["wellbores"] == 5
    assert counts["wells"] == 4

    second = await run_ingest(session, data_dir, "north_sea")
    assert (second.files_ingested, second.files_skipped) == (0, 7)
    assert await table_counts(session) == counts

    wellbores = {w.name: w for w in (await session.execute(select(m.Wellbore))).scalars()}
    side = wellbores["9/9-A-1 A"]
    assert side.parent_id == wellbores["9/9-A-1"].id
    assert side.kickoff_md_m == 1000
    assert side.kind == "sidetrack"

    stations = (
        (
            await session.execute(
                select(m.TrajectoryStation)
                .where(m.TrajectoryStation.wellbore_id == wellbores["9/9-A-1"].id)
                .order_by(m.TrajectoryStation.md_m)
            )
        )
        .scalars()
        .all()
    )
    typo = next(s for s in stations if s.md_m == 1100)
    assert typo.reported_tvd_rejected
    assert typo.tvd_m == pytest.approx(500 + 600 * COS30, abs=0.01)
    side_stations = (
        (
            await session.execute(
                select(m.TrajectoryStation).where(m.TrajectoryStation.wellbore_id == side.id)
            )
        )
        .scalars()
        .all()
    )
    assert {s.inherited for s in side_stations} == {True, False}
    assert all(s.md_m < 1000 for s in side_stations if s.inherited)

    tops = {
        (w, t.name): t
        for t in (await session.execute(select(m.FormationTop))).scalars()
        for w in [next(n for n, wb in wellbores.items() if wb.id == t.wellbore_id)]
    }
    assert tops[("9/9-A-1", "Balder Fm")].md_top_m == 1400
    assert tops[("9/9-A-1 A", "Utsira Fm")].inherited_from_id == wellbores["9/9-A-1"].id
    assert tops[("9/9-A-1 A", "Balder Fm")].inherited_from_id is None
    correlated = tops[("9/9-B-1", "Utsira Fm")]
    assert correlated.source == "correlated"
    assert correlated.tvdss_top_m == pytest.approx(280.0)  # median of 270, 280, 290 TVDSS
    assert ("9/9-A-1", "Kai Fm") not in tops

    activity = (
        await session.execute(select(m.Activity).where(m.Activity.state == "fail"))
    ).scalar_one()
    assert (activity.seq, activity.duration_h, activity.state_detail) == (
        1,
        4.0,
        "circulation loss",
    )

    payload = await reports.collect_data_qc(session)
    gate = payload["gate"]
    assert gate["wellbores"] == gate["with_coordinates"] == gate["with_trajectory"] == 5
    assert gate["with_formation_tops"] == 5
    assert gate["with_correlated_tops_only"] == ["9/9-B-1"]
    by_name = {w["wellbore"]: w for w in payload["wellbores"]}
    assert by_name["9/9-A-1"]["tvd_error_at_td_m"] == pytest.approx(0.0, abs=0.05)
    reports.write_data_qc(payload, tmp_path)
    assert "| 9/9-B-1 |" in (tmp_path / "data_qc.md").read_text()


def test_parser_fidelity_report_on_synthetic_corpus(data_dir: Path, tmp_path: Path) -> None:
    assert cli_main(["fidelity", "--data-dir", str(data_dir), "--reports-dir", str(tmp_path)]) == 0
    result = reports.parser_fidelity(data_dir)
    assert result.files == 7
    assert result.coverage_pct == 100.0
    assert result.unmapped_values == 0
    assert "PASS" in (tmp_path / "parser_fidelity.md").read_text()


async def test_rule_extraction_on_the_loaded_field(
    session: AsyncSession, data_dir: Path, tmp_path: Path
) -> None:
    await run_ingest(session, data_dir, "north_sea")  # no-op if the first test already loaded
    stats = await run_extraction(session)
    again = await run_extraction(session)
    assert (stats.events, stats.evidence) == (again.events, again.evidence)
    assert stats.by_hazard["LOST_CIRCULATION"] == 1

    event = (
        await session.execute(select(m.Event).where(m.Event.hazard == "LOST_CIRCULATION"))
    ).scalar_one()
    assert (event.md_top_m, event.depth_source, event.detected_by) == (1450, "text", "code+text")
    assert event.formation == "Balder Fm"
    assert event.tvd_top_m == pytest.approx(500 + 950 * COS30, abs=0.5)
    assert event.npt_h == 4.0
    assert event.confidence_tier == "rule"

    spans = (
        (
            await session.execute(
                select(m.EventEvidence.char_start, m.EventEvidence.char_end, m.Activity.comments)
                .join(m.Activity, m.Activity.id == m.EventEvidence.activity_id)
                .where(
                    m.EventEvidence.event_id == event.id, m.EventEvidence.char_start.is_not(None)
                )
            )
        )
        .tuples()
        .all()
    )
    assert spans
    assert all((text or "")[start:end].lower().startswith("loss") for start, end, text in spans)

    payload = await extraction_report.collect(session)
    assert (
        payload["evidence_spans"]["total"] == payload["evidence_spans"]["resolving_to_source_text"]
    )
    extraction_report.write(payload, tmp_path)
    assert "LOST_CIRCULATION" in (tmp_path / "extraction_rules.md").read_text()
