from __future__ import annotations

from app.config.settings import SecuritySettings
from app.security.jwt_tokens import create_access_token, decode_access_token


def _settings(**overrides) -> SecuritySettings:
    overrides.setdefault("jwt_secret", "test-jwt-secret-at-least-32-bytes-long")
    return SecuritySettings(**overrides)


def test_decode_roundtrips_username_and_role():
    settings = _settings()
    token, expires_in = create_access_token(username="alice", role="trace_admin", settings=settings)

    claims = decode_access_token(token, settings)

    assert claims is not None
    assert claims["sub"] == "alice"
    assert claims["role"] == "trace_admin"
    assert expires_in == settings.jwt_expires_minutes * 60


def test_decode_rejects_token_signed_with_different_secret():
    settings = _settings()
    other_settings = _settings(jwt_secret="a-completely-different-32-byte-secret")
    token, _ = create_access_token(username="alice", role="user", settings=other_settings)

    assert decode_access_token(token, settings) is None


def test_decode_rejects_expired_token():
    settings = _settings(jwt_expires_minutes=0)
    token, _ = create_access_token(username="alice", role="user", settings=settings)

    assert decode_access_token(token, settings) is None


def test_decode_rejects_garbage_token():
    settings = _settings()
    assert decode_access_token("not.a.jwt", settings) is None
