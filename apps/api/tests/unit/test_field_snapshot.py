"""Field snapshot built from raw files (no database), its queries and its API endpoints."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from drillsage.api.app import create_app
from drillsage.core.config import Settings
from drillsage.domain.trajectory import TrajectoryStation, TvdSource
from drillsage.field.schemas import FieldSnapshot
from drillsage.field.snapshot import build_snapshot, plan_position, read_snapshot, write_snapshot
from drillsage.field.store import EventQuery, EventSort, query_events
from tests.conftest import open_client
from tests.fixtures.field import COS30, synthetic_field


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("field")
    synthetic_field(path)
    return path


@pytest.fixture(scope="module")
def snapshot(data_dir: Path) -> FieldSnapshot:
    return build_snapshot(data_dir, "north_sea", field="Synthetic")


def test_snapshot_matches_the_database_pipeline(snapshot: FieldSnapshot) -> None:
    stats = snapshot.stats
    assert (stats.wellbores, stats.reports) == (5, 6)  # the resubmitted day counts once
    assert stats.events == 1
    assert stats.evidence_spans >= 1

    event = snapshot.events[0]
    assert (event.hazard, event.wellbore, event.md_top_m) == ("LOST_CIRCULATION", "9/9-A-1", 1450)
    assert event.formation == "Balder Fm"
    assert event.npt_h == 4.0
    assert event.geological
    kb = next(w for w in snapshot.wellbores if w.name == "9/9-A-1").kb_elevation_m
    assert kb is not None
    assert event.tvdss_top_m == pytest.approx(500 + 950 * COS30 - kb, abs=0.5)
    line = event.evidence[0]
    span = line.spans[0]
    assert line.text[span.start : span.end].lower().startswith("loss")
    assert event.evidence_lines_total >= len(event.evidence)

    lc = next(h for h in snapshot.hazards if h.hazard == "LOST_CIRCULATION")
    assert (lc.events, lc.wellbores) == (1, 1)
    assert len(snapshot.hazards) == 12
    assert [f.order for f in snapshot.formations] == sorted(f.order for f in snapshot.formations)


def test_wellbores_carry_geometry_tops_and_honest_offsets(snapshot: FieldSnapshot) -> None:
    by_name = {w.name: w for w in snapshot.wellbores}
    a1 = by_name["9/9-A-1"]
    assert a1.trajectory[0].md_m < a1.trajectory[-1].md_m
    assert a1.trajectory[-1].easting_m > a1.easting_m  # the slant hole heads east (azimuth 90)
    assert {t.name for t in a1.tops} >= {"Utsira Fm", "Balder Fm"}
    assert a1.events == 1

    sidetrack = by_name["9/9-A-1 A"]
    assert sidetrack.parent_name == "9/9-A-1"
    before = {o.name: o.completed_before_spud for o in sidetrack.offsets}
    assert before["9/9-A-1"]  # the parent finished before the sidetrack started
    assert not {o.name: o.completed_before_spud for o in a1.offsets}["9/9-A-1 A"]
    distances = [o.surface_distance_m for o in a1.offsets]
    assert distances == sorted(distances)


def test_plan_position_interpolates_and_clamps() -> None:
    def station(md: float, north: float, east: float) -> TrajectoryStation:
        return TrajectoryStation(
            md_m=md,
            incl_deg=0,
            azi_deg=0,
            tvd_m=md,
            north_m=north,
            east_m=east,
            dls_deg_per_30m=0,
            tvd_mincurv_m=md,
            tvd_reported_m=None,
            tvd_source=TvdSource.MINIMUM_CURVATURE,
            reported_rejected=False,
            inherited=False,
        )

    stations = [station(0, 0, 0), station(100, 10, 20)]
    assert plan_position(stations, 50) == (5, 10)
    assert plan_position(stations, -5) == (0, 0)
    assert plan_position(stations, 500) == (10, 20)


def test_queries_filter_sort_and_page(snapshot: FieldSnapshot) -> None:
    events = snapshot.events
    assert query_events(events, EventQuery(hazard="LOST_CIRCULATION")).total == 1
    assert query_events(events, EventQuery(hazard="STUCK_PIPE")).total == 0
    assert query_events(events, EventQuery(q="LOSSES 10")).total == 1
    assert query_events(events, EventQuery(q="kick")).total == 0
    assert query_events(events, EventQuery(severity_min=4)).total == 0
    assert query_events(events, EventQuery(geological=False)).total == 0
    page = query_events(events, EventQuery(sort=EventSort.DEPTH, limit=1000, offset=-3))
    assert (page.limit, page.offset, page.npt_h) == (100, 0, 4.0)


def test_snapshot_round_trips_through_the_file(snapshot: FieldSnapshot, tmp_path: Path) -> None:
    path = write_snapshot(snapshot, tmp_path)
    assert path.exists()
    assert not path.with_suffix(".tmp").exists()
    assert read_snapshot(tmp_path) == snapshot


@pytest.fixture
async def client(
    snapshot: FieldSnapshot, unit_settings: Settings, tmp_path: Path
) -> AsyncIterator[httpx.AsyncClient]:
    write_snapshot(snapshot, tmp_path)
    settings = unit_settings.model_copy(update={"data_dir": tmp_path})
    async for c in open_client(create_app(settings)):
        yield c


async def test_endpoints_serve_the_snapshot(client: httpx.AsyncClient) -> None:
    overview = (await client.get("/api/v1/field")).json()
    assert overview["field"] == "Synthetic"
    assert overview["events"][0]["hazard"] == "LOST_CIRCULATION"
    assert "evidence" not in overview["events"][0]

    page = (await client.get("/api/v1/events", params={"q": "  ", "sort": "npt"})).json()
    assert page["total"] == 1
    event_id = page["items"][0]["id"]
    event = (await client.get(f"/api/v1/events/{event_id}")).json()
    assert event["evidence"]

    missing = await client.get("/api/v1/events/9999")
    assert missing.status_code == 404
    assert missing.headers["content-type"] == "application/problem+json"
    assert (await client.get("/api/v1/events", params={"severity_min": 9})).status_code == 422


async def test_missing_snapshot_is_a_503_problem(unit_settings: Settings, tmp_path: Path) -> None:
    settings = unit_settings.model_copy(update={"data_dir": tmp_path})
    async for c in open_client(create_app(settings)):
        response = await c.get("/api/v1/field")
        assert response.status_code == 503
        assert "make snapshot" in response.json()["detail"]
