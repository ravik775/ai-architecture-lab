import time
from typing import Any

from litellm import completion
from litellm import exceptions as litellm_exceptions
from opentelemetry import trace
from pydantic import ValidationError

from app.ai.models import (
    AIRequest,
    ExecutionContext,
    ProviderResponse,
    ResponseModel,
    TokenUsage,
)
from app.config import settings
from app.exceptions import LLMProviderError
from app.llm.base import LLMService
from app.observability.metrics import (
    record_llm_failure,
    record_validation_failure,
)

tracer = trace.get_tracer("expense-ai")


class LiteLLMService(LLMService):
    LITELLM_EXCEPTIONS = (
        litellm_exceptions.RateLimitError,
        litellm_exceptions.AuthenticationError,
        litellm_exceptions.Timeout,
        litellm_exceptions.APIConnectionError,
    )

    def invoke(
        self,
        context: ExecutionContext,
        request: AIRequest,
        response_model: type[ResponseModel],
    ) -> ProviderResponse[ResponseModel]:
        provider = context.provider
        if provider is None:
            raise LLMProviderError("No LLM provider selected.")

        started_at = time.perf_counter()

        with tracer.start_as_current_span("llm.provider.call") as span:
            self._set_request_span_attributes(span, context)

            try:
                response = completion(
                    **self._build_completion_params(provider, request, response_model)
                )

                latency_ms = self._elapsed_ms(started_at)
                content = self._extract_content(response, provider)
                result = response_model.model_validate_json(content)
                usage = self._extract_usage(response)

                self._set_success_span_attributes(span, usage)

                return ProviderResponse(
                    content=result,
                    provider=provider.name,
                    model=provider.model,
                    latency_ms=latency_ms,
                    usage=usage,
                )

            except ValidationError as exc:
                record_validation_failure(provider.name, provider.model)
                self._mark_span_failure(span, exc)
                raise LLMProviderError(
                    "Structured response validation failed."
                ) from exc

            except self.LITELLM_EXCEPTIONS as exc:
                record_llm_failure(provider.name, provider.model, type(exc).__name__)
                self._mark_span_failure(span, exc)
                raise LLMProviderError("LiteLLM provider error.") from exc

    @staticmethod
    def _build_completion_params(
        provider,
        request: AIRequest,
        response_model: type[ResponseModel],
    ) -> dict[str, Any]:
        rt = settings.runtime

        return {
            "model": provider.model,
            "api_key": provider.api_key,
            "api_base": provider.base_url,
            "timeout": rt.timeout_seconds,
            "temperature": rt.temperature,
            "max_tokens": rt.max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": request.prompt,
                }
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "schema": response_model.model_json_schema(),
                    "strict": True,
                },
            },
        }

    @staticmethod
    def _extract_content(response, provider) -> str:
        content = response.choices[0].message.content
        if not content:
            record_llm_failure(provider.name, provider.model, "EmptyResponse")
            raise LLMProviderError("Empty response from provider.")
        return content

    @staticmethod
    def _extract_usage(response) -> TokenUsage | None:
        usage = getattr(response, "usage", None)
        if not usage:
            return None

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

    @staticmethod
    def _set_request_span_attributes(span, context: ExecutionContext) -> None:
        provider = context.provider

        span.set_attribute("llm.provider", provider.name)
        span.set_attribute("llm.model", provider.model)
        span.set_attribute("llm.base_url", provider.base_url or "litellm_default")
        span.set_attribute("llm.attempt", context.attempt)

    @staticmethod
    def _set_success_span_attributes(span, usage: TokenUsage | None) -> None:
        span.set_attribute("llm.status", "success")

        if usage is None:
            return

        span.set_attribute("llm.prompt_tokens", usage.prompt_tokens)
        span.set_attribute("llm.completion_tokens", usage.completion_tokens)
        span.set_attribute("llm.total_tokens", usage.total_tokens)

    @staticmethod
    def _mark_span_failure(span, exc: Exception) -> None:
        span.record_exception(exc)
        span.set_attribute("llm.status", "failure")
        span.set_attribute("error.type", type(exc).__name__)

    @staticmethod
    def _elapsed_ms(started_at: float) -> float:
        return round((time.perf_counter() - started_at) * 1000, 2)