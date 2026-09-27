"""Domain exceptions and their mapping to RFC 7807 `application/problem+json` responses.

Raise these from services; never raise `HTTPException` outside the API layer.
"""

from http import HTTPStatus
from typing import Any, ClassVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from drillsage.core.logging import current_request_id, get_logger

PROBLEM_JSON = "application/problem+json"
_PROBLEM_BASE = "https://drillsage.dev/problems/"

log = get_logger(__name__)


class Problem(BaseModel):
    """RFC 7807 problem details, extended with the correlation id."""

    type: str = Field(description="URI identifying the problem type")
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    request_id: str | None = None
    errors: list[dict[str, Any]] | None = Field(
        default=None, description="Field-level validation errors, when applicable"
    )


class DrillSageError(Exception):
    """Base class for expected, user-facing failures."""

    status: ClassVar[HTTPStatus] = HTTPStatus.INTERNAL_SERVER_ERROR
    slug: ClassVar[str] = "internal"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFoundError(DrillSageError):
    status = HTTPStatus.NOT_FOUND
    slug = "not-found"


class ConflictError(DrillSageError):
    status = HTTPStatus.CONFLICT
    slug = "conflict"


class InvalidInputError(DrillSageError):
    status = HTTPStatus.UNPROCESSABLE_ENTITY
    slug = "invalid-input"


class DependencyUnavailableError(DrillSageError):
    status = HTTPStatus.SERVICE_UNAVAILABLE
    slug = "dependency-unavailable"


def _problem_response(problem: Problem) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(exclude_none=True),
        media_type=PROBLEM_JSON,
    )


def _problem(
    request: Request,
    status: HTTPStatus,
    slug: str,
    detail: str | None,
    errors: list[dict[str, Any]] | None = None,
) -> Problem:
    return Problem(
        type=_PROBLEM_BASE + slug,
        title=status.phrase,
        status=status.value,
        detail=detail,
        instance=request.url.path,
        request_id=current_request_id(),
        errors=errors,
    )


async def _handle_drillsage_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DrillSageError)  # noqa: S101 - narrowed by registration
    return _problem_response(_problem(request, exc.status, exc.slug, exc.detail))


async def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101 - narrowed by registration
    status = HTTPStatus(exc.status_code)
    slug = status.phrase.lower().replace(" ", "-")
    return _problem_response(_problem(request, status, slug, str(exc.detail)))


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101 - narrowed by registration
    errors = [
        {"loc": list(err.get("loc", ())), "msg": err.get("msg"), "type": err.get("type")}
        for err in exc.errors()
    ]
    return _problem_response(
        _problem(
            request,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "invalid-input",
            "Request validation failed",
            errors,
        )
    )


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled_exception", path=request.url.path, exc_type=type(exc).__name__)
    return _problem_response(
        _problem(request, HTTPStatus.INTERNAL_SERVER_ERROR, "internal", "Unexpected error")
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DrillSageError, _handle_drillsage_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected)
