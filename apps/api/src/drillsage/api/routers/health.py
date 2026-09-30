"""Liveness, readiness and service metadata endpoints."""

import asyncio
from typing import Literal

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from drillsage import __version__
from drillsage.api.deps import DatabaseDep, SettingsDep
from drillsage.core.config import VOLVE_ATTRIBUTION
from drillsage.field.store import SnapshotStore

CheckStatus = Literal["ok", "unavailable"]

router = APIRouter(tags=["health"])


class Liveness(BaseModel):
    status: Literal["ok"] = "ok"


class Readiness(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, CheckStatus]


class ServiceMeta(BaseModel):
    name: str
    version: str
    environment: str
    local_only: bool
    data_attribution: str


@router.get("/healthz", response_model=Liveness, summary="Liveness probe")
async def healthz() -> Liveness:
    """The process is up and serving requests. Checks no dependencies."""
    return Liveness()


@router.get(
    "/readyz",
    response_model=Readiness,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": Readiness}},
    summary="Readiness probe",
)
async def readyz(
    request: Request, database: DatabaseDep, settings: SettingsDep
) -> Readiness | JSONResponse:
    """Ready to take traffic: every hard dependency answers.

    The field snapshot is always required (every screen reads it). The database is required
    unless the service runs in snapshot-only mode, where it is not used at all.
    """
    store: SnapshotStore = request.app.state.snapshots
    checks: dict[str, CheckStatus] = {
        "field_snapshot": "ok" if await asyncio.to_thread(store.available) else "unavailable"
    }
    if not settings.snapshot_only:
        checks["database"] = "ok" if await database.ping() else "unavailable"
    ready = all(state == "ok" for state in checks.values())
    report = Readiness(
        status="ready" if ready else "not_ready", checks=dict(sorted(checks.items()))
    )
    if ready:
        return report
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=report.model_dump()
    )


@router.get("/api/v1/meta", response_model=ServiceMeta, summary="Service metadata")
async def meta(settings: SettingsDep) -> ServiceMeta:
    return ServiceMeta(
        name=settings.app_name,
        version=__version__,
        environment=settings.environment.value,
        local_only=settings.local_only,
        data_attribution=VOLVE_ATTRIBUTION,
    )
