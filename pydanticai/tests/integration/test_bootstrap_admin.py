from __future__ import annotations

from starlette.testclient import TestClient

from tests.integration.conftest import _prepare_env


def _bootstrap_client(tmp_path, monkeypatch, *, username="admin", password="bootstrap-password-123", role="trace_admin"):
    get_settings = _prepare_env(tmp_path, monkeypatch)
    monkeypatch.setenv("SECURITY__BOOTSTRAP_ADMIN_USERNAME", username)
    monkeypatch.setenv("SECURITY__BOOTSTRAP_ADMIN_PASSWORD", password)
    monkeypatch.setenv("SECURITY__BOOTSTRAP_ADMIN_ROLE", role)
    get_settings.cache_clear()

    from app.main import create_app

    app = create_app(mount_ui=False)
    return TestClient(app), get_settings


def test_no_default_user_exists_without_explicit_bootstrap_config(app_client):
    """The shared `app_client` fixture never sets SECURITY__BOOTSTRAP_ADMIN_*
    - this is a regression guard that no default/guessable account is
    silently created."""
    for guess in (("admin", "admin"), ("admin", "password"), ("trace_admin", "trace_admin")):
        resp = app_client.post("/v1/auth/login", json={"username": guess[0], "password": guess[1]})
        assert resp.status_code == 401


def test_bootstrap_admin_can_log_in_with_configured_credentials(tmp_path, monkeypatch):
    client, get_settings = _bootstrap_client(tmp_path, monkeypatch)
    with client:
        resp = client.post("/v1/auth/login", json={"username": "admin", "password": "bootstrap-password-123"})
        assert resp.status_code == 200
        assert resp.json()["role"] == "trace_admin"
    get_settings.cache_clear()


def test_bootstrap_admin_role_is_configurable(tmp_path, monkeypatch):
    client, get_settings = _bootstrap_client(tmp_path, monkeypatch, role="user")
    with client:
        resp = client.post("/v1/auth/login", json={"username": "admin", "password": "bootstrap-password-123"})
        assert resp.json()["role"] == "user"
    get_settings.cache_clear()


def test_bootstrap_admin_survives_restart_without_erroring(tmp_path, monkeypatch):
    """Bootstrapping runs on every startup - the second run must silently
    skip (UserAlreadyExistsError caught, not raised) rather than crash the
    app or reset the password."""
    client1, get_settings = _bootstrap_client(tmp_path, monkeypatch)
    with client1:
        assert client1.post(
            "/v1/auth/login", json={"username": "admin", "password": "bootstrap-password-123"}
        ).status_code == 200

    from app.main import create_app

    get_settings.cache_clear()
    app2 = create_app(mount_ui=False)
    with TestClient(app2) as client2:
        resp = client2.post("/v1/auth/login", json={"username": "admin", "password": "bootstrap-password-123"})
        assert resp.status_code == 200
    get_settings.cache_clear()
