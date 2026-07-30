from abc import ABC, abstractmethod
from app.ai.models import AIRequest, ExecutionContext
from app.ai.models import ProviderResponse, TResponse

class LLMService(ABC):

    @abstractmethod
    def invoke(self, context: ExecutionContext, request: AIRequest) -> ProviderResponse:
        """
       Executes a single LLM request.

       Providers should NOT perform logging,
       metrics or tracing.

       They only communicate with the provider
       and return ProviderResponse.
       """
        pass