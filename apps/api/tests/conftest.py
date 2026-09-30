"""Shared fixtures.

Unit tests run the real ASGI app (with its lifespan) against a database URL that is
guaranteed to be unreachable, so they never depend on Docker. Integration tests use the
configured database and are skipped when it is not reachable.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from pydantic import PostgresDsn

from drillsage.api.app import create_app
from drillsage.core.config import Environment, Settings

UNREACHABLE_DB = PostgresDsn("postgresql+asyncpg://nobody:nothing@127.0.0.1:1/none")


@pytest.fixture
def unit_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,  # no field snapshot unless a test writes one
        environment=Environment.TEST,
        database_url=UNREACHABLE_DB,
        database_connect_timeout_s=0.5,
        _env_file=None,
    )


async def open_client(
    app: FastAPI, *, raise_app_exceptions: bool = True
) -> AsyncIterator[httpx.AsyncClient]:
    """Run the app's lifespan and yield a client bound to it.

    Starlette re-raises unhandled errors after sending the 500 response (so servers can log
    them); pass `raise_app_exceptions=False` to assert on that response instead.
    """
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
async def client(unit_settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    async for c in open_client(create_app(unit_settings)):
        yield c
