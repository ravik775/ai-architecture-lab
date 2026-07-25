import time

from litellm import completion
from litellm import exceptions as litellm_exceptions
from pydantic import ValidationError

from app.ai.models import AIRequest, ProviderResponse
from app.config import settings
from app.exceptions import LLMProviderError
from app.llm.base import LLMService, T


class LiteLLMService(LLMService):

    LITELLM_EXCEPTIONS = (
        litellm_exceptions.RateLimitError,
        litellm_exceptions.AuthenticationError,
        litellm_exceptions.Timeout,
        litellm_exceptions.APIConnectionError,
    )

    def invoke(self, request: AIRequest, response_model: type[T] ) -> ProviderResponse[T]:
        schema = response_model.model_json_schema()
        start = time.perf_counter()
        try:
            response = completion(
                model=settings.ai.llm_model,
                api_key=settings.ai.model_api_key,
                timeout=settings.ai.timeout,
                temperature=0,
                max_tokens=settings.ai.max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": request.prompt,
                    }
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_model.__name__,
                        "schema": schema,
                        "strict": True,
                    },
                },
            )

            latency_ms = round((time.perf_counter() - start) * 1000, 2,)
            content = response.choices[0].message.content
            if not content:
                raise LLMProviderError("Empty response from provider.")
            result = response_model.model_validate_json(content)
            return ProviderResponse(
                content=result,
                provider=settings.ai.llm_provider,
                model=settings.ai.llm_model,
                latency_ms=latency_ms,
                usage=self._extract_usage(response),
            )

        except ValidationError as e:
            raise LLMProviderError(
                f"Structured response validation failed: {e}"
            ) from e

        except self.LITELLM_EXCEPTIONS as e:
            raise LLMProviderError(
                f"LiteLLM provider error: {e}"
            ) from e

    @staticmethod
    def _extract_usage(response) -> dict[str, int] | None:
        usage = getattr(response, "usage", None)

        if usage is None:
            return None

        keys = ("prompt_tokens", "completion_tokens", "total_tokens")

        if isinstance(usage, dict):
            return {
                key: int(usage.get(key, 0))
                for key in keys
            }

        return {
            key: int(getattr(usage, key, 0))
            for key in keys
        }