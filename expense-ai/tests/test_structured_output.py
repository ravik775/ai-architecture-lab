from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.exceptions import LLMProviderError
from app.llm.litellm_service import LiteLLMService
from app.llm.mockllm_service import MockLLMService
from app.schemas import AIExpenseAnalysis, Expense, ExpenseRequest
from app.services.expense_service import ExpenseService


class FakeStructuredLLM:
    def chat(self, prompt: str) -> str:
        return "unused"

    def structured_chat(self, prompt: str, response_model: type[AIExpenseAnalysis]):
        return response_model.model_validate(
            {
                "summary": "Validated structured summary.",
                "largest_category": "Travel",
                "high_value_expenses": ["Hotel - 12000"],
                "recommendations": ["Check policy limit."],
                "suspicious": ["Hotel - 12000"],
            }
        )


def test_expense_service_uses_structured_output():
    service = ExpenseService(llm_service=FakeStructuredLLM())
    request = ExpenseRequest(
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
    )

    response = service.analyze(request)

    assert response.summary == "Validated structured summary."
    assert response.suspicious == ["Hotel - 12000"]
    assert response.total_amount == 12000


def test_mock_llm_structured_chat_returns_pydantic_model():
    result = MockLLMService().structured_chat(
        prompt="Analyze expenses",
        response_model=AIExpenseAnalysis,
    )

    assert isinstance(result, AIExpenseAnalysis)
    assert result.summary == "Expenses analyzed successfully."
    assert result.suspicious == []


def test_litellm_structured_chat_retries_after_invalid_response():
    invalid_response = _completion_response('{"summary": ""}')
    valid_response = _completion_response(
        """
{
  "summary": "Valid summary",
  "largest_category": "Travel",
  "high_value_expenses": [],
  "recommendations": [],
  "suspicious": []
}
"""
    )

    with patch("app.llm.litellm_service.settings") as mock_settings, patch(
        "app.llm.litellm_service.completion",
        side_effect=[invalid_response, valid_response],
    ) as mock_completion:
        mock_settings.ai.llm_provider = "litellm"
        mock_settings.ai.llm_model = "test-model"
        mock_settings.ai.model_api_key = "test-key"
        mock_settings.ai.timeout = 30
        mock_settings.ai.max_tokens = 200
        mock_settings.ai.max_retries = 1

        result = LiteLLMService().structured_chat(
            prompt="Analyze expenses",
            response_model=AIExpenseAnalysis,
        )

    assert result.summary == "Valid summary"
    assert mock_completion.call_count == 2


def test_litellm_structured_chat_raises_after_retry_exhaustion():
    invalid_response = _completion_response('{"summary": ""}')

    with patch("app.llm.litellm_service.settings") as mock_settings, patch(
        "app.llm.litellm_service.completion",
        return_value=invalid_response,
    ):
        mock_settings.ai.llm_provider = "litellm"
        mock_settings.ai.llm_model = "test-model"
        mock_settings.ai.model_api_key = "test-key"
        mock_settings.ai.timeout = 30
        mock_settings.ai.max_tokens = 200
        mock_settings.ai.max_retries = 1

        with pytest.raises(LLMProviderError):
            LiteLLMService().structured_chat(
                prompt="Analyze expenses",
                response_model=AIExpenseAnalysis,
            )


def _completion_response(content: str):
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response