import time
from typing import Any

from litellm import completion, _turn_on_debug
from litellm import exceptions as litellm_exceptions
from opentelemetry.trace import Status, StatusCode, get_tracer
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

tracer = get_tracer("expense-ai")
#   _turn_on_debug()


class LiteLLMService(LLMService):
    LITELLM_EXCEPTIONS = (
        litellm_exceptions.RateLimitError,
        litellm_exceptions.AuthenticationError,
        litellm_exceptions.Timeout,
        litellm_exceptions.APIConnectionError,
        litellm_exceptions.APIError,
        litellm_exceptions.ServiceUnavailableError,
        litellm_exceptions.BadRequestError,
    )

    def invoke(self, context: ExecutionContext, request: AIRequest) -> ProviderResponse:
        provider = context.provider
        if not provider:
            raise LLMProviderError("No LLM provider selected.")

        started_at = time.perf_counter()

        # Span name follows the GenAI convention: "{operation} {model}"
        with tracer.start_as_current_span(f"chat {provider.model}") as span:
            self._set_request_span_attributes(span, context)

            try:
                params = self._build_completion_params(provider, request, context.response_model)
                response = completion(**params)

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
                self._set_success_span_attributes(span, usage, choice)

                return ProviderResponse(content=content, parsed=parsed, provider=provider.name, model=provider.model,
                                        latency_ms=latency_ms, usage=usage)

            except self.LITELLM_EXCEPTIONS as exc:
                record_llm_failure(provider.name, provider.model, type(exc).__name__)
                self._mark_span_failure(span, exc)
                raise LLMProviderError(
                    f"LiteLLM provider error: {exc.message if hasattr(exc, 'message') else str(exc)}") from exc
            except Exception as exc:
                self._mark_span_failure(span, exc)
                if not isinstance(exc, LLMProviderError):
                    record_llm_failure(provider.name, provider.model, type(exc).__name__)
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

        # --- LangSmith run classification ---
        # Tells LangSmith's OTel ingestion to render this as an LLM run card
        # (input/output, tokens, cost) instead of a generic chain/span node.
        span.set_attribute("langsmith.span.kind", "LLM")

        # --- OTel GenAI semantic conventions (vendor-neutral; also read by
        # Datadog/Honeycomb/Grafana if you ever fan out to a second backend) ---
        span.set_attribute("gen_ai.operation.name", "chat")
        span.set_attribute("gen_ai.provider.name", provider.name)
        span.set_attribute("gen_ai.system", provider.name)  # legacy key, some ingestion paths still key off this
        span.set_attribute("gen_ai.request.model", provider.model)

        # --- app-specific context, kept alongside the standard attributes ---
        span.set_attribute("llm.base_url", provider.base_url or "litellm_default")
        span.set_attribute("llm.attempt", context.attempt)

    @staticmethod
    def _set_success_span_attributes(span, usage: TokenUsage | None, choice=None) -> None:
        span.set_status(Status(StatusCode.OK))
        span.set_attribute("llm.status", "success")

        finish_reason = getattr(choice, "finish_reason", None) if choice else None
        if finish_reason:
            span.set_attribute("gen_ai.response.finish_reasons", [finish_reason])

        if usage is None:
            return

        span.set_attribute("gen_ai.usage.input_tokens", usage.prompt_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", usage.completion_tokens)
        # kept for backward compatibility with existing dashboards/queries
        span.set_attribute("llm.prompt_tokens", usage.prompt_tokens)
        span.set_attribute("llm.completion_tokens", usage.completion_tokens)
        span.set_attribute("llm.total_tokens", usage.total_tokens)

    @staticmethod
    def _mark_span_failure(span, exc: Exception) -> None:
        span.record_exception(exc)
        span.set_status(Status(StatusCode.ERROR, str(exc)))  # was missing — this is what makes LangSmith/APM flag the run as failed
        span.set_attribute("llm.status", "failure")
        span.set_attribute("error.type", type(exc).__name__)

    @staticmethod
    def _elapsed_ms(started_at: float) -> float:
        return round((time.perf_counter() - started_at) * 1000, 2)