from app.llm.base import LLMService
from app.ai.models import ResponseModel


from abc import ABC, abstractmethod
from app.ai.models import AIRequest
from app.ai.models import ProviderResponse, ResponseModel

class MockLLMService(LLMService):

    def invoke(self, request: AIRequest, response_model: type[ResponseModel]) -> ProviderResponse[ResponseModel]:
       """
       Executes a single LLM request.

       Providers should NOT perform logging,
       metrics or tracing.

       They only communicate with the provider
       and return ProviderResponse.
       """
       return response_model.model_validate(
            {
                "summary": "Expenses analyzed successfully.",
                "largest_category": "Infrastructure",
                "high_value_expenses": ["Cloud Hosting - 200.0"],
                "recommendations": ["Review recurring cloud costs."],
                "suspicious": [],
            }
        )