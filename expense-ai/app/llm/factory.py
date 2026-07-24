from app.config import settings
from app.llm.litellm_service import LiteLLMService
from app.llm.mockllm_service import MockLLMService
from app.llm.base import LLMService

class LLMFactory:

    @staticmethod
    def create() -> LLMService:
        match settings.provider:
            case "litellm":
                return LiteLLMService()
            case "mock":
                return MockLLMService()
            case _:
                raise ValueError(f"Unsupported provider: {settings.provider}")

