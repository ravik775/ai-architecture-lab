from __future__ import annotations

INTERNAL_TOKEN = "test-internal-token"  # matches conftest.py's SECURITY__INTERNAL_API_TOKEN


def _create_user(client, *, username="alice", password="correct horse battery", role="user"):
    return client.post(
        "/internal/auth/users",
        json={"username": username, "password": password, "role": role},
        headers={"X-Internal-Token": INTERNAL_TOKEN},
    )


def test_create_user_requires_internal_token(app_client):
    resp = app_client.post("/internal/auth/users", json={"username": "bob", "password": "whatever123"})
    assert resp.status_code == 401


def test_create_user_then_login_succeeds(app_client):
    create_resp = _create_user(app_client)
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["username"] == "alice"
    assert body["role"] == "user"

    login_resp = app_client.post("/v1/auth/login", json={"username": "alice", "password": "correct horse battery"})
    assert login_resp.status_code == 200
    token_body = login_resp.json()
    assert token_body["token_type"] == "bearer"
    assert token_body["role"] == "user"
    assert token_body["access_token"]


def test_create_user_duplicate_username_conflicts(app_client):
    assert _create_user(app_client).status_code == 201
    resp = _create_user(app_client)
    assert resp.status_code == 409


def test_login_wrong_password_is_unauthorized(app_client):
    _create_user(app_client)
    resp = app_client.post("/v1/auth/login", json={"username": "alice", "password": "wrong password"})
    assert resp.status_code == 401


def test_login_unknown_user_is_unauthorized(app_client):
    resp = app_client.post("/v1/auth/login", json={"username": "nobody", "password": "irrelevant"})
    assert resp.status_code == 401


def test_me_with_valid_token_returns_identity(app_client):
    _create_user(app_client, username="carol", role="trace_admin")
    login_resp = app_client.post("/v1/auth/login", json={"username": "carol", "password": "correct horse battery"})
    token = login_resp.json()["access_token"]

    resp = app_client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == {"username": "carol", "role": "trace_admin"}


def test_me_without_token_is_unauthorized(app_client):
    resp = app_client.get("/v1/auth/me")
    assert resp.status_code == 401


def test_me_with_garbage_token_is_unauthorized(app_client):
    resp = app_client.get("/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401
