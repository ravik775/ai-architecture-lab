from litellm import completion
from app.config import settings
from app.llm.base import LLMService

class LiteLLMService(LLMService):
    def chat(self, prompt: str) -> str:
        print(f"{prompt = }")
        response = completion(model=settings.model, api_key=settings.model_api_key, api_base=settings.model_base_url,
                                   messages=[{
                                       "role": "user",
                                       "content": prompt
                                   }])
        # Correct path: choices -> message -> content
        message = response.choices[0].message
        return message.content if message and message.content else "No summary generated."