from app.config import settings, Providers
from app.llm.litellm_service import LiteLLMService
from app.llm.mockllm_service import MockLLMService
from app.llm.base import LLMService

class LLMFactory:

    @staticmethod
    def create() -> LLMService:
        match settings.ai.llm_provider:
            case Providers.LITELLM:
                return LiteLLMService()
            case Providers.MOCK:
                return MockLLMService()
            case _:
                raise ValueError(f"Unsupported provider: {settings.ai.llm_provider}")

