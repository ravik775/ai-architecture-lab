import json
import logging
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.models import (
    AIExpenseAnalysis,
    AIRequest,
    ExecutionContext,
    Provider,
    TokenUsage,
)
from app.llm.litellm_service import LiteLLMService
from app.observability.cost import estimate_llm_cost_usd
from app.observability.logging import log_info
from app.observability.middleware import RequestContextMiddleware
from app.schemas import Expense, ExpenseRequest


def test_structured_logging_redacts_sensitive_fields(caplog):
    with caplog.at_level(logging.INFO, logger="expense_ai"):
        log_info(
            "test.redaction",
            submitted_by="Ravi",
            model_api_key="secret",
            token_usage={
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        )

    payload = json.loads(caplog.records[0].message)

    assert payload["submitted_by"] == "[REDACTED]"
    assert payload["model_api_key"] == "[REDACTED]"
    assert payload["token_usage"]["total_tokens"] == 15


def test_request_id_is_returned_in_success_response():
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/health")
    def health():
        return {"status": "UP"}

    response = TestClient(app).get(
        "/health",
        headers={"X-Request-ID": "req-123"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-123"


def test_cost_estimation_uses_litellm_model_metadata():
    cost = estimate_llm_cost_usd(
        model="test-model",
        usage=TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        ),
        model_costs={
            "test-model": {
                "input_cost_per_token": 0.000001,
                "output_cost_per_token": 0.000002,
            }
        },
    )

    assert cost == 0.0002


def test_litellm_invoke_returns_provider_response():
    parsed = AIExpenseAnalysis(
        summary="Valid summary",
        largest_category="Travel",
        policy_flags=[],
        requires_approval=False,
        suspicious=[],
    )

    valid_response = _completion_response(
        parsed=parsed,
        content=None,
        usage={
            "prompt_tokens": 3,
            "completion_tokens": 4,
            "total_tokens": 7,
        },
    )

    request = _ai_request()
    context = _execution_context(request)

    with patch(
        "app.llm.litellm_service.completion",
        return_value=valid_response,
    ):
        result = LiteLLMService().invoke(context, request)

    assert result.parsed == parsed
    assert result.provider == "test-provider"
    assert result.model == "test-model"
    assert result.usage.total_tokens == 7


def _ai_request() -> AIRequest[ExpenseRequest]:
    return AIRequest[ExpenseRequest](
        request=ExpenseRequest(
            submitted_by="Ravi",
            currency="INR",
            submitted_date=datetime.now(timezone.utc),
            expenses=[
                Expense(
                    description="Hotel stay",
                    amount=12000,
                    quantity=1,
                    merchant="Hotel ABC",
                    category="Travel",
                )
            ],
        ),
        prompt="Analyze expenses",
        prompt_type="summary",
    )


def _execution_context(request: AIRequest[ExpenseRequest]) -> ExecutionContext:
    return ExecutionContext(
        request=request,
        response_model=AIExpenseAnalysis,
        provider=Provider(
            name="test-provider",
            model="test-model",
            api_key="test-key",
        ),
    )


def _completion_response(parsed=None, content: str | None = None, usage: dict | None = None):
    message = type("Message", (), {})()
    message.parsed = parsed
    message.content = content

    choice = type("Choice", (), {})()
    choice.message = message

    response = type("Response", (), {})()
    response.choices = [choice]
    response.usage = usage

    return response