from abc import ABC, abstractmethod
from typing import TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)
class LLMService(ABC):
    @abstractmethod
    def chat(self, prompt: str) -> str:
        """Execute the Prompt using llm and return response"""
        pass

    @abstractmethod
    def structured_chat(self, prompt: str, response_model: type[T]) -> T:
        pass