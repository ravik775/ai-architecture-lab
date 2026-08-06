"""
End-to-end route integration tests (FastAPI TestClient) - auth/RBAC,
force-trace, chat happy/error paths, health endpoints.

`app.main` resolves Settings once at import time (`settings = get_settings()`,
memoized via `lru_cache`), so the env vars below MUST be set before this
module's `from app.main import app` runs - that's why they're set at
module scope, before any local import, rather than in a fixture.
"""
import os

os.environ.setdefault("OBSERVABILITY_PROVIDER", "console")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("TRACE_SAMPLING_RATIO", "1.0")
os.environ.setdefault(
    "API_KEYS", "full-key:chat,force_trace;chat-only-key:chat"
)

from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.llm.chain as chain_module  # noqa: E402
from app.main import app  # noqa: E402


def _fake_response(content="Hello!"):
    return SimpleNamespace(
        model="openrouter/test-model",
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2, total_tokens=5),
    )


@pytest.fixture(autouse=True)
def _fake_litellm(monkeypatch):
    monkeypatch.setattr(chain_module.litellm, "completion", lambda **kw: _fake_response())
    monkeypatch.setattr(chain_module.litellm, "completion_cost", lambda **kw: 0.0001)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ------------------------------------------------------------------ root --
def test_root_endpoint(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["service"]


# ---------------------------------------------------------------- health --
def test_health_live_requires_no_auth(client):
    r = client.get("/health/live")
    assert r.status_code == 200


def test_health_summary_requires_no_auth(client):
    r = client.get("/health/summary")
    assert r.status_code == 200


# ------------------------------------------------------------------ auth --
def test_chat_without_api_key_401(client):
    r = client.post("/chat", json={"session_id": "t1", "message": "hi"})
    assert r.status_code == 401


def test_chat_with_wrong_api_key_401(client):
    r = client.post(
        "/chat", json={"session_id": "t1", "message": "hi"}, headers={"X-API-Key": "not-a-real-key"}
    )
    assert r.status_code == 401


def test_chat_with_valid_key_succeeds(client):
    r = client.post(
        "/chat",
        json={"session_id": "t1", "message": "hi"},
        headers={"X-API-Key": "chat-only-key"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "Hello!"
    assert body["session_id"] == "t1"
    assert body["trace_id"]


def test_history_and_delete_require_auth_too(client):
    assert client.get("/chat/t1/history").status_code == 401
    assert client.delete("/chat/t1").status_code == 401

    assert client.get("/chat/t1/history", headers={"X-API-Key": "chat-only-key"}).status_code == 200
    assert client.delete("/chat/t1", headers={"X-API-Key": "chat-only-key"}).status_code == 200


# --------------------------------------------------------------- history --
def test_chat_then_history_shows_the_turn(client):
    client.post(
        "/chat",
        json={"session_id": "t2", "message": "remember this"},
        headers={"X-API-Key": "chat-only-key"},
    )
    r = client.get("/chat/t2/history", headers={"X-API-Key": "chat-only-key"})
    assert r.status_code == 200
    history = r.json()["history"]
    assert history[0]["content"] == "remember this"
    assert history[1]["content"] == "Hello!"


def test_delete_clears_history(client):
    client.post(
        "/chat",
        json={"session_id": "t3", "message": "hi"},
        headers={"X-API-Key": "chat-only-key"},
    )
    client.delete("/chat/t3", headers={"X-API-Key": "chat-only-key"})
    r = client.get("/chat/t3/history", headers={"X-API-Key": "chat-only-key"})
    assert r.json()["history"] == []


# --------------------------------------------------------- force-trace RBAC --
def test_force_trace_header_ignored_without_permission_still_succeeds(client):
    # chat-only-key lacks force_trace - header should be silently ignored,
    # not rejected (the whole point: a stray header doesn't break the call).
    r = client.post(
        "/chat",
        json={"session_id": "t4", "message": "hi"},
        headers={"X-API-Key": "chat-only-key", "X-Force-Trace": "true"},
    )
    assert r.status_code == 200


def test_force_trace_header_honored_with_permission(client):
    r = client.post(
        "/chat",
        json={"session_id": "t5", "message": "hi"},
        headers={"X-API-Key": "full-key", "X-Force-Trace": "true"},
    )
    assert r.status_code == 200
    assert r.json()["trace_id"]


# --------------------------------------------------------------- failure --
def test_chat_llm_failure_returns_502(client, monkeypatch):
    def boom(**kw):
        raise RuntimeError("simulated upstream failure")

    monkeypatch.setattr(chain_module.litellm, "completion", boom)

    r = client.post(
        "/chat",
        json={"session_id": "t6", "message": "hi"},
        headers={"X-API-Key": "chat-only-key"},
    )
    assert r.status_code == 502


def test_chat_rejects_empty_message(client):
    r = client.post(
        "/chat",
        json={"session_id": "t7", "message": ""},
        headers={"X-API-Key": "chat-only-key"},
    )
    assert r.status_code == 422  # pydantic min_length=1 validation


def test_chat_rejects_oversized_message(client):
    r = client.post(
        "/chat",
        json={"session_id": "t8", "message": "x" * 4001},
        headers={"X-API-Key": "chat-only-key"},
    )
    assert r.status_code == 422  # pydantic max_length=4000 validation


def test_chat_rejects_whitespace_only_message(client):
    # min_length=1 alone lets " " through - the field_validator guardrail
    # (OWASP LLM01) is what actually catches this.
    r = client.post(
        "/chat",
        json={"session_id": "t9", "message": "   "},
        headers={"X-API-Key": "chat-only-key"},
    )
    assert r.status_code == 422


# -------------------------------------------------------- rate limiting --
def test_chat_rate_limit_exceeded_returns_429(client, monkeypatch):
    import app.api.routes as routes_module
    from app.security.rate_limit import TokenBucketRateLimiter

    # Tiny budget so the second call in this test trips it, without
    # touching every other test's shared 30/min default.
    tiny_limiter = TokenBucketRateLimiter(requests_per_minute=60, capacity=1)
    monkeypatch.setattr(routes_module, "get_rate_limiter", lambda _rate: tiny_limiter)

    ok = client.post(
        "/chat",
        json={"session_id": "rl1", "message": "hi"},
        headers={"X-API-Key": "chat-only-key"},
    )
    assert ok.status_code == 200

    limited = client.post(
        "/chat",
        json={"session_id": "rl1", "message": "hi again"},
        headers={"X-API-Key": "chat-only-key"},
    )
    assert limited.status_code == 429
    assert "Retry-After" in limited.headers


def test_chat_rate_limit_is_per_key_not_global(client, monkeypatch):
    # Per-key isolation itself (two distinct key_ids each getting their own
    # bucket) is covered at the unit level in test_rate_limit.py -
    # test_different_keys_have_independent_buckets. Here we only need to
    # confirm routes.py passes the *authenticated principal's* key_id (not
    # some shared/global key) into limiter.check() - do that by asserting
    # the limiter recorded a bucket under the expected key_id rather than
    # picking two real API keys, since both "full-key" and "chat-only-key"
    # happen to share the same last-4-chars key_id ("...-key") by
    # coincidence of this fixture's naming.
    import app.api.routes as routes_module
    from app.security.rate_limit import TokenBucketRateLimiter

    tiny_limiter = TokenBucketRateLimiter(requests_per_minute=60, capacity=5)
    monkeypatch.setattr(routes_module, "get_rate_limiter", lambda _rate: tiny_limiter)

    r = client.post(
        "/chat",
        json={"session_id": "rl2", "message": "hi"},
        headers={"X-API-Key": "chat-only-key"},
    )
    assert r.status_code == 200
    assert "...-key" in tiny_limiter._buckets
