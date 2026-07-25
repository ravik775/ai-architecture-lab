from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.exceptions import LLMProviderError
from app.observability.context import get_request_id
from app.observability.logging import log_error


async def llm_provider_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Safely cast or assume exc is LLMProviderError since this handler is registered for it
    error_message = str(exc)
    request_id = get_request_id() or "no-request-id"
    content = {
        "error": "AI_PROVIDER_ERROR",
        "message": "AI analysis is temporarily unavailable.",
        "request_id": request_id,
    }

    log_error("api.error.llm_provider", path=request.url.path, method=request.method, error=error_message)
    return JSONResponse(status_code=502, content=content, headers={"X-Request-ID": request_id},)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(LLMProviderError, llm_provider_error_handler)