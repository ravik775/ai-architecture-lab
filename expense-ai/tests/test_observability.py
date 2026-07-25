import json
import logging

from app.observability.context import get_request_id, reset_request_id, set_request_id
from app.observability.logging import log_info


def test_request_id_context_round_trip():
    token = set_request_id("req-123")

    try:
        assert get_request_id() == "req-123"
    finally:
        reset_request_id(token)

    assert get_request_id() is None


def test_structured_log_includes_request_id(caplog):
    token = set_request_id("req-456")

    try:
        with caplog.at_level(logging.INFO, logger="expense_ai"):
            log_info("test.event", provider="litellm", latency_ms=12.3)
    finally:
        reset_request_id(token)

    payload = json.loads(caplog.records[0].message)

    assert payload["event"] == "test.event"
    assert payload["request_id"] == "req-456"
    assert payload["provider"] == "litellm"
    assert payload["latency_ms"] == 12.3