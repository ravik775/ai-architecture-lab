from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.ai.models import AIExpenseAnalysis, AIRequest, ExecutionContext, Provider
from app.exceptions import LLMProviderError, StructuredOutputError
from app.llm.litellm_service import LiteLLMService
from app.llm.mockllm_service import MockLLMService
from app.llm.response_parser import ResponseParser
from app.schemas import Expense, ExpenseRequest


def test_response_parser_accepts_valid_structured_json():
    response = MagicMock()
    response.parsed = None
    response.content = """
    {
      "summary": "Validated structured summary.",
      "largest_category": "Travel",
      "policy_flags": [
        "Hotel Approval Policy: Hotel amount requires review."
      ],
      "requires_approval": true,
      "suspicious": ["Hotel - 12000"]
    }
    """

    result = ResponseParser().parse(response, AIExpenseAnalysis)

    assert result.summary == "Validated structured summary."
    assert result.largest_category == "Travel"
    assert result.policy_flags == [
        "Hotel Approval Policy: Hotel amount requires review."
    ]
    assert result.requires_approval is True
    assert result.suspicious == ["Hotel - 12000"]


def test_response_parser_rejects_invalid_structured_json():
    response = MagicMock()
    response.parsed = None
    response.content = '{"summary": ""}'

    with pytest.raises(StructuredOutputError):
        ResponseParser().parse(response, AIExpenseAnalysis)


def test_mock_llm_service_returns_provider_response():
    request = _ai_request()
    context = _execution_context(
        request=request,
        provider=Provider(
            name="mock",
            model="mock-model",
            api_key="",
        ),
    )

    result = MockLLMService().invoke(context, request)

    assert result.provider == "mock"
    assert result.model == "mock-model"
    assert result.content is None
    assert result.parsed is not None
    assert isinstance(result.parsed, AIExpenseAnalysis)
    assert result.parsed.summary == "Expenses analyzed successfully."
    assert result.parsed.largest_category == "Infrastructure"
    assert result.parsed.policy_flags == []
    assert result.parsed.requires_approval is False
    assert result.parsed.suspicious == []


def test_litellm_service_wraps_unexpected_provider_error():
    request = _ai_request()
    context = _execution_context(
        request=request,
        provider=Provider(
            name="test-provider",
            model="test-model",
            api_key="test-key",
        ),
    )

    with patch(
            "app.llm.litellm_service.completion",
            side_effect=Exception("provider failed"),
    ):
        with pytest.raises(LLMProviderError):
            LiteLLMService().invoke(context, request)


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


def _execution_context(
        request: AIRequest[ExpenseRequest],
        provider: Provider,
) -> ExecutionContext:
    return ExecutionContext(
        request=request,
        response_model=AIExpenseAnalysis,
        provider=provider,
    )