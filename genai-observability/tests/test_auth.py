"""API-key auth + RBAC - app/security/auth.py."""
import asyncio

import pytest
from fastapi import HTTPException

from app.config import Settings
from app.security import auth as auth_module


def run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------- _parse_api_keys --
def test_parse_api_keys_empty_string():
    assert auth_module._parse_api_keys("") == {}
    assert auth_module._parse_api_keys("   ") == {}


def test_parse_api_keys_single_key_multiple_permissions():
    keys = auth_module._parse_api_keys("k1:chat,force_trace")
    assert keys == {"k1": frozenset({"chat", "force_trace"})}


def test_parse_api_keys_multiple_entries():
    keys = auth_module._parse_api_keys("k1:chat,force_trace;k2:chat")
    assert keys["k1"] == frozenset({"chat", "force_trace"})
    assert keys["k2"] == frozenset({"chat"})


def test_parse_api_keys_skips_malformed_entry_without_colon():
    # Missing ':' - skipped with a warning, not a crash.
    keys = auth_module._parse_api_keys("this-has-no-colon;k2:chat")
    assert "this-has-no-colon" not in keys
    assert keys == {"k2": frozenset({"chat"})}


def test_parse_api_keys_tolerates_whitespace():
    keys = auth_module._parse_api_keys(" k1 : chat , force_trace ; k2 : chat ")
    assert keys["k1"] == frozenset({"chat", "force_trace"})
    assert keys["k2"] == frozenset({"chat"})


def test_parse_api_keys_empty_permission_list():
    keys = auth_module._parse_api_keys("k1:")
    assert keys["k1"] == frozenset()


# ------------------------------------------------------------- Principal --
def test_principal_has_permission():
    p = auth_module.Principal(key_id="...abcd", permissions=frozenset({"chat"}))
    assert p.has("chat")
    assert not p.has("force_trace")


# --------------------------------------------------------- authenticate() --
def _settings(api_keys: str) -> Settings:
    return Settings(openrouter_api_key="x", api_keys=api_keys)


def test_authenticate_no_keys_configured_is_anonymous_chat_only(monkeypatch):
    monkeypatch.setattr(auth_module, "get_settings", lambda: _settings(""))
    principal = run(auth_module.authenticate(x_api_key=None))
    assert principal.key_id == "anonymous"
    assert principal.has(auth_module.PERMISSION_CHAT)
    assert not principal.has(auth_module.PERMISSION_FORCE_TRACE)


def test_authenticate_missing_header_when_keys_configured_401(monkeypatch):
    monkeypatch.setattr(auth_module, "get_settings", lambda: _settings("k1:chat"))
    with pytest.raises(HTTPException) as exc_info:
        run(auth_module.authenticate(x_api_key=None))
    assert exc_info.value.status_code == 401


def test_authenticate_invalid_key_401(monkeypatch):
    monkeypatch.setattr(auth_module, "get_settings", lambda: _settings("k1:chat"))
    with pytest.raises(HTTPException) as exc_info:
        run(auth_module.authenticate(x_api_key="not-the-right-key"))
    assert exc_info.value.status_code == 401


def test_authenticate_valid_key_lacking_chat_permission_403(monkeypatch):
    monkeypatch.setattr(auth_module, "get_settings", lambda: _settings("k1:force_trace"))
    with pytest.raises(HTTPException) as exc_info:
        run(auth_module.authenticate(x_api_key="k1"))
    assert exc_info.value.status_code == 403


def test_authenticate_valid_key_with_chat_permission_succeeds(monkeypatch):
    monkeypatch.setattr(auth_module, "get_settings", lambda: _settings("key1:chat,force_trace"))
    principal = run(auth_module.authenticate(x_api_key="key1"))
    assert principal.has(auth_module.PERMISSION_CHAT)
    assert principal.has(auth_module.PERMISSION_FORCE_TRACE)
    assert principal.key_id == "...key1"  # last 4 chars of a 4-char key is the whole key here


def test_authenticate_key_id_never_contains_full_long_key(monkeypatch):
    long_key = "sk-super-secret-do-not-log-this-1234"
    monkeypatch.setattr(auth_module, "get_settings", lambda: _settings(f"{long_key}:chat"))
    principal = run(auth_module.authenticate(x_api_key=long_key))
    assert principal.key_id == "...1234"
    assert long_key not in principal.key_id


# ------------------------------------------------------------ auth_enabled --
def test_auth_enabled_reflects_whether_any_keys_configured(monkeypatch):
    monkeypatch.setattr(auth_module, "get_settings", lambda: _settings(""))
    assert auth_module.auth_enabled() is False

    monkeypatch.setattr(auth_module, "get_settings", lambda: _settings("k1:chat"))
    assert auth_module.auth_enabled() is True
