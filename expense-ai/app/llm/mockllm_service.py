from app.llm.base import LLMService
from app.ai.models import TResponse, ExecutionContext

from abc import ABC, abstractmethod
from app.ai.models import AIRequest
from app.ai.models import ProviderResponse, TResponse

class MockLLMService(LLMService):

    def invoke(self, context: ExecutionContext, request: AIRequest) -> ProviderResponse:
       """
       Executes a single LLM request.

       Providers should NOT perform logging,
       metrics or tracing.

       They only communicate with the provider
       and return ProviderResponse.
       """
       mock_data = {
                "summary": "Expenses analyzed successfully.",
                "largest_category": "Infrastructure",
                "high_value_expenses": ["Cloud Hosting - 200.0"],
                "recommendations": ["Review recurring cloud costs."],
                "suspicious": [],
            }
       return ProviderResponse(
                provider="mock",
                model="mock",
                latency_ms=0,
                parsed=context.response_model.model_validate_json(str(mock_data)))