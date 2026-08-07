from __future__ import annotations

from starlette.testclient import TestClient

from tests.integration.conftest import _prepare_env


def _rate_limited_client(tmp_path, monkeypatch, *, limit: int = 3):
    """Builds its own app instance with rate limiting explicitly re-enabled -
    the shared `app_client` fixture disables it (see conftest.py) since most
    tests fire well over 10 requests/minute at TestClient's fixed synthetic
    IP within a single test."""
    get_settings = _prepare_env(tmp_path, monkeypatch)
    # _prepare_env itself sets RATE_LIMIT_ENABLED=false (see conftest.py) -
    # override AFTER it runs, then clear the settings cache again so the
    # override actually takes effect for create_app()'s get_settings() call.
    monkeypatch.setenv("SECURITY__RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("SECURITY__RATE_LIMIT_REQUESTS_PER_MINUTE", str(limit))
    get_settings.cache_clear()

    from app.main import create_app

    app = create_app(mount_ui=False)
    client = TestClient(app)
    return client, get_settings


def test_requests_within_limit_all_succeed(tmp_path, monkeypatch):
    client, get_settings = _rate_limited_client(tmp_path, monkeypatch, limit=3)
    with client:
        for _ in range(3):
            resp = client.get("/v1/locations/countries")
            assert resp.status_code == 200
    get_settings.cache_clear()


def test_requests_over_limit_are_rejected_with_429(tmp_path, monkeypatch):
    client, get_settings = _rate_limited_client(tmp_path, monkeypatch, limit=3)
    with client:
        for _ in range(3):
            assert client.get("/v1/locations/countries").status_code == 200
        over_limit = client.get("/v1/locations/countries")
        assert over_limit.status_code == 429
        assert "Retry-After" in over_limit.headers
    get_settings.cache_clear()


def test_health_check_routes_are_exempt_from_rate_limit(tmp_path, monkeypatch):
    client, get_settings = _rate_limited_client(tmp_path, monkeypatch, limit=2)
    with client:
        for _ in range(5):
            resp = client.get("/health/live")
            assert resp.status_code == 200
    get_settings.cache_clear()


def test_ui_asset_routes_are_exempt_from_rate_limit(tmp_path, monkeypatch):
    """A single /ui page load fires a burst of 15+ background requests for
    NiceGUI's own static assets/socket.io client - none of that is
    user-driven API traffic the rate limiter is meant to police (see
    app/security/rate_limit.py). limit=1 makes this a strong regression
    guard: even one real request would exhaust it if these weren't exempt.

    Deliberately mount_ui=False (matching every other test in this file) -
    the exemption is a path-prefix check in the middleware itself, which
    runs before routing, so it doesn't need the UI actually mounted. Only
    ONE test in the whole suite may mount_ui=True (NiceGUI's process-wide
    singleton - see conftest.py's `app_client_with_ui` docstring); a 404
    here for a route that doesn't exist still proves the point: the
    middleware short-circuits to exempt *before* the 404 would even be
    produced, so it's never counted against the rate-limit bucket."""
    client, get_settings = _rate_limited_client(tmp_path, monkeypatch, limit=1)
    with client:
        for path in (
            "/ui",
            "/ui/_nicegui/3.2.0/static/nicegui.js",
            "/ui/_nicegui/3.2.0/static/socket.io.min.js",
            "/_nicegui/3.2.0/components/some_component.js",
        ):
            resp = client.get(path)
            assert resp.status_code != 429, f"{path} should be exempt from rate limiting"
    get_settings.cache_clear()


def test_rejected_response_still_carries_request_id(tmp_path, monkeypatch):
    client, get_settings = _rate_limited_client(tmp_path, monkeypatch, limit=1)
    with client:
        assert client.get("/v1/locations/countries").status_code == 200
        rejected = client.get("/v1/locations/countries")
        assert rejected.status_code == 429
        assert "x-request-id" in {k.lower() for k in rejected.headers.keys()}
    get_settings.cache_clear()
