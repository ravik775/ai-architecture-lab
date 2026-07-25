from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.exceptions import LLMProviderError
from app.handlers import register_exception_handlers
from app.observability.middleware import RequestContextMiddleware


def test_llm_provider_error_returns_clean_response():
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    @app.get("/boom")
    def boom():
        raise LLMProviderError("provider detail")

    response = TestClient(app).get("/boom", headers={"X-Request-ID": "req-test"})

    assert response.status_code == 502
    assert response.headers["X-Request-ID"] == "req-test"
    assert response.json() == {
        "error": "AI_PROVIDER_ERROR",
        "message": "AI analysis is temporarily unavailable.",
        "request_id": "req-test",
    }