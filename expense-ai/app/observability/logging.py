import json
import logging
from typing import Any

from app.observability.context import get_request_id
from app.observability.redaction import redact_fields

logger = logging.getLogger("expense_ai")


def log_event(level: int, event: str, **fields: Any) -> None:
    payload = {
        "event": event,
        "request_id": get_request_id(),
        **fields,
    }
    logger.log(level, json.dumps(redact_fields(payload), default=str))


def log_info(event: str, **fields: Any) -> None:
    log_event(logging.INFO, event, **fields)


def log_warning(event: str, **fields: Any) -> None:
    log_event(logging.WARNING, event, **fields)


def log_error(event: str, **fields: Any) -> None:
    log_event(logging.ERROR, event, **fields)