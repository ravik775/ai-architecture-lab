from app.llm.base import LLMService

class MockLLMService(LLMService):
    def chat(self, prompt: str) -> str:
       return "Mock"