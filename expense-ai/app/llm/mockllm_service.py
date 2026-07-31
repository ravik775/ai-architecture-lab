from app.llm.base import LLMService
from app.ai.models import AIRequest, ExecutionContext, ProviderResponse


class MockLLMService(LLMService):
    def invoke(self, context: ExecutionContext, request: AIRequest) -> ProviderResponse:
        mock_data = {
            "summary": "Expenses approved successfully.",
            "largest_category": "Infrastructure",
            "policy_flags": [],
            "requires_approval": False,
            "suspicious": [],
        }

        parsed = context.response_model.model_validate(mock_data)

        return ProviderResponse(
            provider=context.provider.name if context.provider else "mock",
            model=context.provider.model if context.provider else "mock-model",
            latency_ms=0,
            content=None,
            parsed=parsed,
            usage=None,
        )