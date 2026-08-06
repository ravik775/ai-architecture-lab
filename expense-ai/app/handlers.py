from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from app.exceptions import LLMProviderError, GuardrailViolation, StructuredOutputError, LLMNotFoundError
from app.observability.context import get_request_id
from app.observability.logging import log_error

# Configuration mapping exception types to response schemas and log details
ERROR_CONFIG = {
    LLMProviderError: {
        "status_code": status.HTTP_502_BAD_GATEWAY,
        "error": "AI_PROVIDER_ERROR",
        "message": "AI analysis is temporarily unavailable.",
        "event": "api.error.llm_provider",
    },
    StructuredOutputError: {
        "status_code": status.HTTP_502_BAD_GATEWAY,
        "error": "AI_PROVIDER_ERROR",
        "message": "AI analysis is temporarily unavailable.",
        "event": "api.error.structured_output",
    },
    GuardrailViolation: {
        "status_code": status.HTTP_400_BAD_REQUEST,
        "error": "PROMPT_REJECTED",
        "message": "Input violates AI safety policy.",
        "event": "api.guardrail.rejected",
    },
    LLMNotFoundError: {
        "status_code": status.HTTP_404_NOT_FOUND,
        "error": "NOT_FOUND",
        "message": None,  # Will fallback to str(exc)
        "event": "api.error.not_found",
    },
}

default_config = {
        "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "error": "INTERNAL_SERVER_ERROR",
        "message": "An unexpected error occurred.",
        "event": "api.error.unhandled",
    }

async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Unified exception handler for all registered application errors."""
    config = ERROR_CONFIG.get(type(exc), default_config)
    log_error(config["event"], path=request.url.path, method=request.method, error=str(exc), ) # Log exception event cleanly
    request_id = get_request_id() or "no-request-id"
    payload = { "error": config["error"], "message": config["message"] or str(exc), "request_id": request_id, }
    return JSONResponse(status_code=config["status_code"], content=payload, headers={"X-Request-ID": request_id}, )


def register_exception_handlers(app: FastAPI) -> None:
    for exc_type in ERROR_CONFIG:
        app.add_exception_handler(exc_type, global_exception_handler)