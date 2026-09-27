"""Liveness, readiness and service metadata endpoints."""

from typing import Literal

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from drillsage import __version__
from drillsage.api.deps import DatabaseDep, SettingsDep

VOLVE_ATTRIBUTION = (
    "Contains data from the Volve field dataset, released by Equinor and the Volve "
    "licence partners under CC BY-NC-SA 4.0."
)

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
async def readyz(database: DatabaseDep) -> Readiness | JSONResponse:
    """Ready to take traffic: every hard dependency answers."""
    database_ok = await database.ping()
    report = Readiness(
        status="ready" if database_ok else "not_ready",
        checks={"database": "ok" if database_ok else "unavailable"},
    )
    if database_ok:
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
