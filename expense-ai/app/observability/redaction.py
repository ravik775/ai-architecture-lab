from typing import Any


SENSITIVE_FIELD_NAMES = {
    "api_key",
    "authorization",
    "cookie",
    "email",
    "employee",
    "model_api_key",
    "password",
    "prompt",
    "secret",
    "submitted_by",
    "token",
}

SAFE_FIELD_NAMES = {
    "completion_tokens",
    "prompt_length",
    "prompt_preview",
    "prompt_tokens",
    "token_type",
    "token_usage",
    "total_tokens",
}


def redact_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _is_sensitive_key(key) else redact_fields(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [redact_fields(item) for item in value]

    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    if normalized in SAFE_FIELD_NAMES:
        return False
    return any(sensitive in normalized for sensitive in SENSITIVE_FIELD_NAMES)