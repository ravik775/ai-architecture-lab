from __future__ import annotations

import asyncio

import pytest
from starlette.testclient import TestClient


def _prepare_env(tmp_path, monkeypatch):
    db_path = (tmp_path / "test.db").as_posix()
    monkeypatch.setenv("DATABASE__URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("SECURITY__INTERNAL_API_TOKEN", "test-internal-token")
    monkeypatch.setenv("SCHEDULER__ENABLED", "false")
    monkeypatch.setenv("OBSERVABILITY__OTEL_ENABLED", "false")
    # A real socket server per test app instance is unnecessary risk/
    # flakiness; the registry itself is directly inspectable, and the one
    # test that needs a live server enables it explicitly with port 0
    # (OS-assigned free port).
    monkeypatch.setenv("OBSERVABILITY__METRICS_SERVER_ENABLED", "false")
    # Enabled by default (10/min) - most integration tests fire well over
    # 10 requests at "testclient" (TestClient's fixed synthetic IP) within
    # a single test; the one test that exercises the limiter enables it
    # explicitly. See tests/integration/test_rate_limit.py.
    monkeypatch.setenv("SECURITY__RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("SECURITY__JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")

    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    from app.infrastructure.database.models import Base
    from app.infrastructure.database.seed import seed
    from app.infrastructure.database.session import Database

    async def _prepare() -> None:
        db = Database(settings.database)
        async with db.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await db.dispose()
        await seed()

    asyncio.run(_prepare())
    return get_settings


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    """`mount_ui=False`: NiceGUI's `ui.run_with()` mounts onto a
    process-wide singleton whose middleware stack can only be built once
    per process - see `create_app()`'s docstring. None of the tests using
    this fixture touch `/ui/`; the one that does uses
    `app_client_with_ui` instead, which is the only place in the whole
    suite that mounts the UI, avoiding the singleton conflict entirely."""
    get_settings = _prepare_env(tmp_path, monkeypatch)

    from app.main import create_app

    app = create_app(mount_ui=False)
    with TestClient(app) as client:
        yield client

    get_settings.cache_clear()


@pytest.fixture()
def app_client_with_ui(tmp_path, monkeypatch):
    get_settings = _prepare_env(tmp_path, monkeypatch)

    from app.main import create_app

    app = create_app(mount_ui=True)
    with TestClient(app) as client:
        yield client

    get_settings.cache_clear()
