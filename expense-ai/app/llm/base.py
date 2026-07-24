from abc import ABC, abstractmethod

class LLMService(ABC):
    @abstractmethod
    def chat(self, prompt: str) -> str:
        """Execute the Prompt using llm and return response"""
        pass