from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.exceptions import LLMProviderError, GuardrailViolation
from app.observability.context import get_request_id
from app.observability.logging import log_error


def _error_handler(request: Request, exc: Exception, content: dict, status_code: int) -> JSONResponse:
    request_id = get_request_id() or "no-request-id"
    content["request_id"] = request_id
    return JSONResponse(status_code=400, content=content, headers={"X-Request-ID": request_id},)


async def llm_provider_error_handler(request: Request, exc: Exception) -> JSONResponse:
    log_error("api.error.llm_provider", path=request.url.path, method=request.method, error= str(exc))

    return _error_handler(request, exc, {
        "error": "AI_PROVIDER_ERROR",
        "message": "AI analysis is temporarily unavailable."}, 500)

async def llm_guardrail_error_handler(request: Request, exc: Exception) -> JSONResponse:
    log_error("api.guardrail.rejected", path=request.url.path, method=request.method, reason= "blocked_phrase")
    return _error_handler(request, exc, {
        "error": "PROMPT_REJECTED",
        "message": "Input violates AI safety policy."}, 400)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(LLMProviderError, llm_provider_error_handler)
    app.add_exception_handler(GuardrailViolation, llm_guardrail_error_handler)