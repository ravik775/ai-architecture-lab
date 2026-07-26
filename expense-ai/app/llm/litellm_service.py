import time

from litellm import completion
from litellm import exceptions as litellm_exceptions
from pydantic import ValidationError

from app.ai.models import AIRequest, ProviderResponse, TokenUsage, ResponseModel, ExecutionContext
from app.config import settings
from app.exceptions import LLMProviderError
from app.llm.base import LLMService


class LiteLLMService(LLMService):

    LITELLM_EXCEPTIONS = (
        litellm_exceptions.RateLimitError,
        litellm_exceptions.AuthenticationError,
        litellm_exceptions.Timeout,
        litellm_exceptions.APIConnectionError,
    )

    def invoke(self, context: ExecutionContext, request: AIRequest, response_model: type[ResponseModel] ) -> ProviderResponse[ResponseModel]:
        schema = response_model.model_json_schema()
        start = time.perf_counter()
        try:
            provider = context.provider
            rt = settings.runtime
            response = completion(
                model=provider.model,
                api_key=provider.api_key,
                timeout=rt.timeout_seconds,
                temperature=rt.temperature,
                max_tokens=rt.max_tokens,
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
                provider=provider.name,
                model=provider.model,
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
    def _extract_usage(response) -> TokenUsage | None:
        usage = getattr(response, "usage", None)
        if usage:
            if isinstance(usage, dict):
                return TokenUsage(
                    prompt_tokens=int(usage.get("prompt_tokens", 0)),
                    completion_tokens=int(usage.get("completion_tokens", 0)),
                    total_tokens=int(usage.get("total_tokens", 0)),
                )

            return TokenUsage(
                prompt_tokens=int(getattr(usage, "prompt_tokens", 0)),
                completion_tokens=int(getattr(usage, "completion_tokens", 0)),
                total_tokens=int(getattr(usage, "total_tokens", 0)),
            )
        return None