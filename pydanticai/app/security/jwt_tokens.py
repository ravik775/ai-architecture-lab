"""JWT issuance/verification - a single shared HS256 secret
(`SecuritySettings.jwt_secret`), no rotation or revocation. Demo-scope only
(see `app/security/__init__.py`).

Claims are intentionally minimal: `sub` (username) and `role`. `role` is
what `app/observability/sampling.py` checks to gate the `force_trace`
sampling override - see that module's docstring for why the token has to
travel via OTel baggage rather than the usual `Authorization` header for
that one specific use case.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.config.settings import SecuritySettings


def create_access_token(*, username: str, role: str, settings: SecuritySettings) -> tuple[str, int]:
    """Returns (token, expires_in_seconds)."""
    expires_in = settings.jwt_expires_minutes * 60
    now = datetime.now(timezone.utc)
    claims = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str, settings: SecuritySettings) -> dict | None:
    """Returns the claims dict, or None on any invalid/expired/malformed
    token - callers treat every failure mode the same way (401), so there's
    no value in distinguishing them here."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
