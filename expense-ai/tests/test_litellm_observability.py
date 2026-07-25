from unittest.mock import MagicMock, patch

from app.llm.litellm_service import LiteLLMService
from app.schemas import AIExpenseAnalysis


def test_structured_chat_logs_retry_and_success(caplog):
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
""",
        usage={"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
    )

    with patch("app.llm.litellm_service.settings") as mock_settings, patch(
        "app.llm.litellm_service.completion",
        side_effect=[invalid_response, valid_response],
    ):
        mock_settings.ai.llm_provider = "litellm"
        mock_settings.ai.llm_model = "test-model"
        mock_settings.ai.model_api_key = "test-key"
        mock_settings.ai.timeout = 30
        mock_settings.ai.max_tokens = 200
        mock_settings.ai.max_retries = 1
        mock_settings.logging.log_prompts = False
        mock_settings.logging.log_responses = False
        mock_settings.logging.log_token_usage = True
        mock_settings.logging.prompt_preview_chars = 300

        with caplog.at_level("INFO", logger="expense_ai"):
            result = LiteLLMService().structured_chat(
                prompt="Analyze expenses",
                response_model=AIExpenseAnalysis,
            )

    assert result.summary == "Valid summary"
    messages = [record.message for record in caplog.records]
    assert any("llm.structured.request.started" in message for message in messages)
    assert any("llm.structured.validation.failed" in message for message in messages)
    assert any("llm.structured.request.completed" in message for message in messages)


def _completion_response(content: str, usage: dict | None = None):
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response