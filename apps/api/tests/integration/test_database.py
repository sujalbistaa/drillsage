"""Integration tests against the real Postgres from `make db-up`.

Skipped automatically when the database is not reachable, so `make test` stays green on
machines without Docker; CI runs them against a Postgres service container.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from drillsage.api.app import create_app
from drillsage.core.config import Environment, Settings
from drillsage.db.session import Database
from tests.conftest import open_client

pytestmark = pytest.mark.integration

API_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def db_settings() -> Settings:
    return Settings(environment=Environment.TEST)


@pytest.fixture(scope="module")
async def database(db_settings: Settings) -> AsyncIterator[Database]:
    db = Database(db_settings)
    if not await db.ping():
        await db.dispose()
        pytest.skip("Postgres not reachable; run `make db-up`")
    yield db
    await db.dispose()


@pytest.fixture(scope="module")
def migrated(database: Database) -> None:
    command.upgrade(Config(str(API_DIR / "alembic.ini")), "head")


async def test_readyz_is_ready_with_live_database(
    db_settings: Settings, database: Database
) -> None:
    async for c in open_client(create_app(db_settings)):
        response: httpx.Response = await c.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok"}}


@pytest.mark.usefixtures("migrated")
async def test_baseline_migration_enables_required_extensions(database: Database) -> None:
    async with database.engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pg_trgm')")
        )
        installed = {row[0] for row in rows}
    assert installed == {"vector", "pg_trgm"}
