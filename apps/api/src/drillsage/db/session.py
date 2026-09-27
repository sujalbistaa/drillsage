"""Async engine and session lifecycle.

One `Database` instance per process, created in the FastAPI lifespan and stored on
`app.state`. Request handlers get a session through the `get_session` dependency.
"""

import asyncio
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from drillsage.core.config import Settings


class Database:
    def __init__(self, settings: Settings) -> None:
        self._engine: AsyncEngine = create_async_engine(
            str(settings.database_url),
            pool_size=settings.database_pool_size,
            pool_pre_ping=True,
            connect_args={"timeout": settings.database_connect_timeout_s},
        )
        self._sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)
        self._ping_timeout_s = settings.database_connect_timeout_s

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._sessionmaker() as session:
            yield session

    async def ping(self) -> bool:
        """True when the database answers `SELECT 1` within the connect timeout."""
        try:
            async with asyncio.timeout(self._ping_timeout_s):
                async with self._engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
        except Exception:  # any driver/network error or timeout means "not ready"
            return False
        return True

    async def dispose(self) -> None:
        await self._engine.dispose()
