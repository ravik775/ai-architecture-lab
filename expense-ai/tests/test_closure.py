import json
import logging
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.llm.litellm_service import LiteLLMService
from app.observability.cost import estimate_llm_cost_usd
from app.observability.logging import log_info
from app.observability.middleware import RequestContextMiddleware
from app.schemas import AIExpenseAnalysis


def test_structured_logging_redacts_sensitive_fields(caplog):
    with caplog.at_level(logging.INFO, logger="expense_ai"):
        log_info(
            "test.redaction",
            submitted_by="Ravi",
            model_api_key="secret",
            token_usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
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

    response = TestClient(app).get("/health", headers={"X-Request-ID": "req-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-123"


def test_cost_estimation_uses_litellm_model_metadata():
    cost = estimate_llm_cost_usd(
        model="test-model",
        usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        model_costs={
            "test-model": {
                "input_cost_per_token": 0.000001,
                "output_cost_per_token": 0.000002,
            }
        },
    )

    assert cost == 0.0002


def test_litellm_structured_chat_records_metrics_and_cost():
    valid_response = _completion_response(
        """
{
  "summary": "Valid summary",
  "largest_category": "Travel",
  "high_value_expenses": [],
  "recommendations": [],
  "suspicious": []
}
""",
        usage={"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
    )

    with patch("app.llm.litellm_service.settings") as mock_settings, patch(
        "app.llm.litellm_service.completion",
        return_value=valid_response,
    ), patch(
        "app.llm.litellm_service.record_llm_success"
    ) as record_success, patch(
        "app.llm.litellm_service.record_token_usage"
    ) as record_tokens, patch(
        "app.llm.litellm_service.record_cost"
    ) as record_cost:
        mock_settings.ai.llm_provider = "litellm"
        mock_settings.ai.llm_model = "test-model"
        mock_settings.ai.model_api_key = "test-key"
        mock_settings.ai.timeout = 30
        mock_settings.ai.max_tokens = 200
        mock_settings.ai.max_retries = 0
        mock_settings.ai.retry_backoff = 0
        mock_settings.logging.log_prompts = False
        mock_settings.logging.log_responses = False
        mock_settings.logging.log_token_usage = True
        mock_settings.logging.prompt_preview_chars = 300

        result = LiteLLMService().structured_chat(
            prompt="Analyze expenses",
            response_model=AIExpenseAnalysis,
        )

    assert result.summary == "Valid summary"
    record_success.assert_called_once()
    record_tokens.assert_called_once()
    record_cost.assert_called_once()


def _completion_response(content: str, usage: dict | None = None):
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response