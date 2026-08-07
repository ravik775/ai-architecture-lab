"""Covers `fetch_login` (app/ui/callbacks.py), the in-process login used by
the `/ui/login` page - see app/ui/pages.py's login_page docstring for why
this exists (a browser-reachable path to the JWT auth REST already has).
"""
from __future__ import annotations

from app.ui.callbacks import fetch_login

INTERNAL_TOKEN = "test-internal-token"  # matches conftest.py's SECURITY__INTERNAL_API_TOKEN


async def test_fetch_login_success(app_client):
    app_client.post(
        "/internal/auth/users",
        json={"username": "dana", "password": "correct horse battery", "role": "trace_admin"},
        headers={"X-Internal-Token": INTERNAL_TOKEN},
    )

    result = await fetch_login(app_client.app, "dana", "correct horse battery")

    assert result["ok"] is True
    assert result["username"] == "dana"
    assert result["role"] == "trace_admin"
    assert result["access_token"]
    assert result["expires_in"] > 0


async def test_fetch_login_wrong_password(app_client):
    app_client.post(
        "/internal/auth/users",
        json={"username": "dana", "password": "correct horse battery"},
        headers={"X-Internal-Token": INTERNAL_TOKEN},
    )

    result = await fetch_login(app_client.app, "dana", "wrong password")

    assert result == {"ok": False, "error": "Invalid username or password."}


async def test_fetch_login_missing_fields(app_client):
    assert (await fetch_login(app_client.app, "", "somepassword"))["ok"] is False
    assert (await fetch_login(app_client.app, "someuser", ""))["ok"] is False
