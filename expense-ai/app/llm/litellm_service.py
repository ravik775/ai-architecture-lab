from litellm import completion
from app.config import settings
from app.llm.base import LLMService

class LiteLLMService(LLMService):
    def chat(self, prompt: str) -> str:
        response = completion.chat(model=settings.model,
                                   messages=[{
                                       "role": "user",
                                       "content": prompt
                                   }])
        return response.choices[0].content