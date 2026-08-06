from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.ai.models import AIExpenseAnalysis, AIRequest, ExecutionContext, Provider
from app.exceptions import LLMProviderError
from app.llm.litellm_service import LiteLLMService
from app.schemas import Expense, ExpenseRequest


def test_litellm_invoke_records_failure_for_empty_response():
    empty_response = _completion_response(parsed=None, content=None)

    request = _ai_request()
    context = _execution_context(request)

    with patch(
        "app.llm.litellm_service.completion",
        return_value=empty_response,
    ), patch(
        "app.llm.litellm_service.record_llm_failure"
    ) as record_failure:
        with pytest.raises(LLMProviderError):
            LiteLLMService().invoke(context, request)

    record_failure.assert_called_once_with(
        "test-provider",
        "test-model",
        "EmptyResponse",
    )


def test_litellm_invoke_returns_usage_for_valid_response():
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
            "prompt_tokens": 20,
            "completion_tokens": 10,
            "total_tokens": 30,
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
    assert result.usage.prompt_tokens == 20
    assert result.usage.completion_tokens == 10
    assert result.usage.total_tokens == 30


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