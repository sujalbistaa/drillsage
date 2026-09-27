"""FastAPI application factory.

Run with: `uvicorn drillsage.api.app:create_app --factory`
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from prometheus_client import make_asgi_app

from drillsage import __version__
from drillsage.api.routers import health
from drillsage.core.config import Settings, get_settings
from drillsage.core.errors import register_exception_handlers
from drillsage.core.logging import configure_logging, get_logger
from drillsage.core.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from drillsage.db.session import Database

log = get_logger(__name__)


def _operation_id(route: APIRoute) -> str:
    """Stable, readable OpenAPI operation ids (they become the generated TS client's names)."""
    return route.name


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.database = Database(settings)
        log.info("startup", environment=settings.environment.value, version=__version__)
        try:
            yield
        finally:
            await app.state.database.dispose()
            log.info("shutdown")

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        summary="Offset-well drilling intelligence for Oil India (SIH26121)",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        generate_unique_id_function=_operation_id,
    )

    register_exception_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["authorization", "content-type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )
    # Added last so it runs outermost: every response, including errors, gets an id.
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router)
    app.mount("/metrics", make_asgi_app())
    return app
