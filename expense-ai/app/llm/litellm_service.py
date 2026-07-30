import time
from typing import Any

from litellm import completion
from litellm import exceptions as litellm_exceptions
from opentelemetry import trace

from app.ai.models import (
    AIRequest,
    ExecutionContext,
    Provider,
    ProviderResponse,
    TokenUsage,
    TResponse,
)
from app.config import settings
from app.exceptions import LLMProviderError
from app.observability.metrics import record_llm_failure
from app.llm.base import LLMService

tracer = trace.get_tracer("expense-ai")

class LiteLLMService(LLMService):
    LITELLM_EXCEPTIONS = (
        litellm_exceptions.RateLimitError,
        litellm_exceptions.AuthenticationError,
        litellm_exceptions.Timeout,
        litellm_exceptions.APIConnectionError,
    )

    def invoke(self, context: ExecutionContext, request: AIRequest) -> ProviderResponse:
        provider = context.provider
        if not provider:
            raise LLMProviderError("No LLM provider selected.")

        started_at = time.perf_counter()

        with (tracer.start_as_current_span("llm.provider.call") as span):
            self._set_request_span_attributes(span, context)

            try:
                # Build completion parameters cleanly
                params = self._build_completion_params(provider, request, context.response_model)
                response = completion(**params)

                # Extract message payload safely
                choice = response.choices[0]
                message = getattr(choice, "message", None)
                if message:
                    parsed = getattr(message, "parsed", None)
                    content = getattr(message, "content", None)
                else:
                    parsed = content = None
                if parsed is None and content is None:
                    record_llm_failure(provider.name, provider.model, "EmptyResponse")
                    raise LLMProviderError("Empty response from provider.")

                latency_ms = self._elapsed_ms(started_at)
                usage = self._extract_usage(response)
                self._set_success_span_attributes(span, usage)

                return ProviderResponse(content=content,parsed=parsed, provider=provider.name, model=provider.model,
                                        latency_ms=latency_ms, usage=usage )

            except self.LITELLM_EXCEPTIONS as exc:
                record_llm_failure(provider.name, provider.model, type(exc).__name__)
                self._mark_span_failure(span, exc)
                raise LLMProviderError(
                    f"LiteLLM provider error: {exc.message if hasattr(exc, 'message') else str(exc)}") from exc
            except Exception as exc:
                # Catch unexpected general exceptions to prevent unhandled tracking gaps
                if not isinstance(exc, LLMProviderError):
                    record_llm_failure(provider.name, provider.model, type(exc).__name__)
                    self._mark_span_failure(span, exc)
                    raise LLMProviderError(f"Unexpected LLM error: {str(exc)}") from exc
                raise


    @staticmethod
    def _build_completion_params(provider: Provider, request: AIRequest, response_model: type[TResponse] | None,) -> dict[str, Any]:
        rt = settings.runtime
        args: dict[str, Any] = {
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
            "response_format": response_model
        }
        return args

    @staticmethod
    def _extract_usage(response) -> TokenUsage | None:
        usage = getattr(response, "usage", None)
        if not usage:
            return None

        # Handle both dictionary-like and object attribute usage patterns cleanly
        get_val = lambda attr: usage.get(attr, 0) if isinstance(usage, dict) else getattr(usage, attr, 0)

        prompt_tokens = int(get_val("prompt_tokens"))
        completion_tokens = int(get_val("completion_tokens"))
        total_tokens = int(get_val("total_tokens"))

        if prompt_tokens == 0 and completion_tokens == 0 and total_tokens == 0:
            return None

        return TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
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