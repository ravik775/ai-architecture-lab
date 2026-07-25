from abc import ABC, abstractmethod
from typing import TypeVar
from pydantic import BaseModel
from app.ai.models import AIRequest
from app.ai.models import ProviderResponse

T = TypeVar("T", bound=BaseModel)

class LLMService(ABC):

    @abstractmethod
    def invoke(self, request: AIRequest, response_model: type[T]) -> ProviderResponse[T]:
        """
       Executes a single LLM request.

       Providers should NOT perform logging,
       metrics or tracing.

       They only communicate with the provider
       and return ProviderResponse.
       """
        pass