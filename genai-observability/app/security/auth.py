"""
Minimal API-key authentication with RBAC, scoped to the `/chat*`
integration point only (per docs/SECURITY-PLAN.md Section 6.4 - health
and metrics endpoints stay open, they carry no cost/data exposure).

Deliberately simple: env-var-configured keys, in-memory, no rotation, no
expiry, no database - this is Phase 1 of the security plan and the brief
was "keep things simple." Swap this for a real identity provider (or at
minimum hashed keys in a proper secrets store) before this leaves a
single trusted deployment - see docs/SECURITY-PLAN.md Phase 3, item 11
(explicitly deferred, not forgotten).
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Header, HTTPException, status

from app.config import get_settings

logger = logging.getLogger("app.security")

PERMISSION_CHAT = "chat"
PERMISSION_FORCE_TRACE = "force_trace"
API_KEY_HEADER_NAME = "X-API-Key"


@dataclass(frozen=True)
class Principal:
    key_id: str  # last 4 chars only - the full key is never logged
    permissions: frozenset[str]

    def has(self, permission: str) -> bool:
        return permission in self.permissions


def _parse_api_keys(raw: str) -> dict[str, frozenset[str]]:
    """
    Format: "key1:chat,force_trace;key2:chat" - semicolon-separated
    entries, each "key:comma,separated,permissions". Malformed entries
    are skipped with a warning rather than crashing the process - a
    config typo shouldn't take the whole service down.
    """
    keys: dict[str, frozenset[str]] = {}
    if not raw.strip():
        return keys
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry:
            continue
        if ":" not in entry:
            logger.warning("Skipping malformed API_KEYS entry (missing ':'): %r", entry)
            continue
        key, _, perms_raw = entry.partition(":")
        key = key.strip()
        perms = frozenset(p.strip() for p in perms_raw.split(",") if p.strip())
        if not key:
            continue
        keys[key] = perms
    return keys


@lru_cache
def _cached_keys(raw: str) -> dict[str, frozenset[str]]:
    # Cached on the raw config string itself, not a global - so changing
    # API_KEYS and restarting the process (the only way settings change
    # in this service) always re-parses correctly, including in tests
    # that construct Settings() directly with a different value.
    return _parse_api_keys(raw)


def auth_enabled() -> bool:
    return bool(_cached_keys(get_settings().api_keys))


async def authenticate(
    x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER_NAME),
) -> Principal:
    """
    FastAPI dependency for the `/chat*` routes. Two distinct failure
    modes, both intentional:
      - No keys configured at all (`API_KEYS` empty) -> auth is disabled
        for this deployment; every caller gets an anonymous principal
        with only the `chat` permission (never `force_trace` - that stays
        opt-in-only via explicit key configuration, even in this mode).
        Loud, one-time warning at startup (main.py); deliberately quiet
        per-request here to avoid log spam once you've been told.
      - Keys ARE configured -> a valid, permitted key is required. Missing
        header and invalid key are both rejected; a valid key lacking the
        `chat` permission is a 403, not a 401 (the difference between "who
        are you" and "you can't do that").
    """
    settings = get_settings()
    keys = _cached_keys(settings.api_keys)

    if not keys:
        return Principal(key_id="anonymous", permissions=frozenset({PERMISSION_CHAT}))

    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-API-Key header")

    # Constant-time compare against every configured key. Iterating a
    # dict doesn't leak anything by itself; what compare_digest buys you
    # is that a wrong guess against any single key can't be distinguished
    # by timing from a near-miss - that's the property that matters.
    for key, perms in keys.items():
        if secrets.compare_digest(x_api_key, key):
            principal = Principal(key_id=f"...{key[-4:]}" if len(key) >= 4 else "...", permissions=perms)
            if not principal.has(PERMISSION_CHAT):
                logger.warning("API key %s lacks 'chat' permission", principal.key_id)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="API key lacks 'chat' permission"
                )
            return principal

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
