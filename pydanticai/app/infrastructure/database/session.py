"""Async SQLAlchemy engine/session lifecycle, WAL mode, and pragmas.

One engine per process, created at app startup and disposed at shutdown
(see `app/main.py` lifespan). Short-lived `AsyncSession`s are created per
unit of work via `session_scope` / the `get_db_session` FastAPI dependency.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import DatabaseSettings


def create_engine(settings: DatabaseSettings) -> AsyncEngine:
    engine = create_async_engine(settings.url, echo=settings.echo, pool_pre_ping=True)

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute(f"PRAGMA busy_timeout={settings.busy_timeout_ms}")
        cursor.close()

    @event.listens_for(engine.sync_engine, "handle_error")
    def _count_busy_errors(exception_context) -> None:  # noqa: ANN001
        message = str(exception_context.original_exception).lower()
        if "locked" in message or "busy" in message:
            from app.observability.metrics import sqlite_busy_errors_total

            sqlite_busy_errors_total.inc()

    return engine


def create_session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


class Database:
    """Holds the app-scoped engine + session factory. One instance lives on
    `app.state.db` for the process lifetime."""

    def __init__(self, settings: DatabaseSettings) -> None:
        self.engine = create_engine(settings)
        self.session_maker = create_session_maker(self.engine)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_maker() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()
