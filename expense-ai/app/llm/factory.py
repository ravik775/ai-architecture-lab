from app.config import settings, LLMImplementation
from app.llm.base import LLMService
from app.llm.litellm_service import LiteLLMService
from app.llm.mockllm_service import MockLLMService


class LLMFactory:

    @staticmethod
    def create() -> LLMService:
        match settings.runtime.implementation:
            case LLMImplementation.LiteLLM:
                return LiteLLMService()
            case LLMImplementation.MOCKLLM:
                return MockLLMService()
            case _:
                raise ValueError("Unsupported runtime implementation")