from __future__ import annotations

import logging


def test_correlation_id_auto_generated_when_not_supplied(app_client):
    resp = app_client.get("/health/live")
    correlation_id = resp.headers.get("x-correlation-id")
    assert correlation_id
    assert len(correlation_id) == 36  # UUID4 string form


def test_correlation_id_echoed_back_when_caller_supplies_one(app_client):
    resp = app_client.get("/health/live", headers={"X-Correlation-ID": "my-friendly-id"})
    assert resp.headers.get("x-correlation-id") == "my-friendly-id"


def test_request_id_and_correlation_id_are_independent(app_client):
    resp = app_client.get(
        "/health/live",
        headers={"X-Correlation-ID": "same-value-for-both-requests"},
    )
    request_id_1 = resp.headers["x-request-id"]
    correlation_id_1 = resp.headers["x-correlation-id"]

    resp2 = app_client.get(
        "/health/live",
        headers={"X-Correlation-ID": "same-value-for-both-requests"},
    )
    request_id_2 = resp2.headers["x-request-id"]
    correlation_id_2 = resp2.headers["x-correlation-id"]

    # correlation_id is caller-controlled and can repeat across requests...
    assert correlation_id_1 == correlation_id_2 == "same-value-for-both-requests"
    # ...but request_id is always freshly app-generated, never reused.
    assert request_id_1 != request_id_2


def test_every_request_produces_a_request_completed_log_line(app_client, caplog):
    with caplog.at_level(logging.INFO, logger="app.request"):
        resp = app_client.get("/health/live", headers={"X-Correlation-ID": "log-line-probe"})

    correlation_id = resp.headers["x-correlation-id"]
    matching = [r for r in caplog.records if r.getMessage() == "request completed"]
    assert matching, "expected a 'request completed' log line for a plain successful GET"
    record = matching[-1]
    assert record.http_route == "/health/live"
    assert record.http_status_code == 200
    assert hasattr(record, "duration_ms")
