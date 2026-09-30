from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from drillsage.api.app import create_app
from drillsage.core.config import Settings
from drillsage.core.errors import PROBLEM_JSON, NotFoundError
from drillsage.field.snapshot import SNAPSHOT_PATH, build_snapshot, write_snapshot
from tests.conftest import open_client
from tests.fixtures.field import synthetic_field


def _synthetic(tmp_path: Path) -> Path:
    raw = tmp_path / "raw-field"
    synthetic_field(raw)
    return raw


async def test_healthz_is_ok_without_dependencies(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_reports_unavailable_dependencies_with_503(client: httpx.AsyncClient) -> None:
    response = await client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "unavailable", "field_snapshot": "unavailable"},
    }


async def test_snapshot_only_mode_is_ready_without_a_database(
    unit_settings: Settings, tmp_path: Path
) -> None:
    snapshot = tmp_path / SNAPSHOT_PATH
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text("{}")  # present but invalid: not ready
    settings = unit_settings.model_copy(update={"snapshot_only": True, "data_dir": tmp_path})
    async for c in open_client(create_app(settings)):
        response = await c.get("/readyz")
        assert response.status_code == 503
        assert response.json()["checks"] == {"field_snapshot": "unavailable"}

        write_snapshot(build_snapshot(_synthetic(tmp_path), "north_sea"), tmp_path)
        response = await c.get("/readyz")
        assert response.status_code == 200
        assert response.json() == {"status": "ready", "checks": {"field_snapshot": "ok"}}


async def test_meta_exposes_version_and_data_attribution(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/meta")).json()
    assert body["name"] == "DrillSage"
    assert body["environment"] == "test"
    assert "Volve" in body["data_attribution"]
    assert "CC BY-NC-SA 4.0" in body["data_attribution"]


async def test_generates_request_id_when_absent(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    request_id = response.headers["x-request-id"]
    assert len(request_id) == 32


async def test_echoes_valid_incoming_request_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz", headers={"x-request-id": "rig-7.abc_123"})
    assert response.headers["x-request-id"] == "rig-7.abc_123"


@pytest.mark.parametrize("bad", ["has space", "x" * 65, "semi;colon", ""])
async def test_replaces_malformed_request_id(client: httpx.AsyncClient, bad: str) -> None:
    response = await client.get("/healthz", headers={"x-request-id": bad})
    assert response.headers["x-request-id"] != bad


async def test_unknown_route_returns_problem_json(client: httpx.AsyncClient) -> None:
    response = await client.get("/no/such/route")
    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON
    problem = response.json()
    assert problem["status"] == 404
    assert problem["instance"] == "/no/such/route"
    assert problem["request_id"] == response.headers["x-request-id"]


async def test_domain_error_maps_to_problem(unit_settings: Settings) -> None:
    app: FastAPI = create_app(unit_settings)

    @app.get("/boom-domain")
    async def boom_domain() -> None:
        raise NotFoundError("Wellbore 15/9-F-99 does not exist")

    async for c in open_client(app):
        response = await c.get("/boom-domain")
    assert response.status_code == 404
    problem = response.json()
    assert problem["type"].endswith("/not-found")
    assert problem["detail"] == "Wellbore 15/9-F-99 does not exist"


async def test_unexpected_error_is_500_problem_without_leaking_details(
    unit_settings: Settings,
) -> None:
    app: FastAPI = create_app(unit_settings)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internal state")

    async for c in open_client(app, raise_app_exceptions=False):
        response = await c.get("/boom")
    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_JSON
    assert "secret" not in response.text


async def test_metrics_endpoint_exposes_request_counters(client: httpx.AsyncClient) -> None:
    await client.get("/healthz")
    body = (await client.get("/metrics/")).text
    assert "drillsage_http_requests_total" in body
    assert 'route="/healthz"' in body
