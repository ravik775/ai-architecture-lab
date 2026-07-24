from app.llm.base import LLMService, T

class MockLLMService(LLMService):
    def chat(self, prompt: str) -> str:
       return "Mock"

    def structured_chat(self, prompt: str, response_model: type[T]) -> T:
        return response_model.model_validate(
            {
                "summary": "Expenses analyzed successfully.",
                "largest_category": "Infrastructure",
                "high_value_expenses": ["Cloud Hosting - 200.0"],
                "recommendations": ["Review recurring cloud costs."],
                "suspicious": [],
            }
        )