import time
from litellm import completion, exceptions as litellm_exceptions, model_cost
from pydantic import ValidationError
from app.config import settings
from app.exceptions import LLMProviderError
from app.llm.base import LLMService, T
from app.observability.cost import estimate_llm_cost_usd
from app.observability.logging import log_error, log_info, log_warning
from app.observability.metrics import (
    record_cost,
    record_llm_success,
    record_retry,
    record_token_usage,
    record_validation_failure,
)


class LiteLLMService(LLMService):
    """Provider-agnostic implementation backed by LiteLLM."""

    LITELLM_EXCEPTIONS = (
        litellm_exceptions.RateLimitError,
        litellm_exceptions.AuthenticationError,
        litellm_exceptions.Timeout,
        litellm_exceptions.APIConnectionError,
    )

    def chat(self, prompt: str) -> str:
        return self._execute_completion(prompt=prompt)

    def structured_chat(self, prompt: str, response_model: type[T]) -> T:
        max_attempts = max(1, settings.ai.max_retries + 1)
        schema = response_model.model_json_schema()
        last_error: Exception | None = None
        prompt_preview = (prompt[: settings.logging.prompt_preview_chars] if settings.logging.log_prompts else None)
        provider, model = settings.ai.llm_provider, settings.ai.llm_model
        log_info(
            "llm.structured.request.started",
            provider=provider,
            model=model,
            response_schema=response_model.__name__,
            prompt_length=len(prompt),
            max_attempts=max_attempts,
            prompt_preview=prompt_preview
        )

        for attempt in range(1, max_attempts + 1):
            try:
                current_prompt = self._build_structured_prompt(prompt, last_error)
                response, latency_ms, usage = self._execute_call(
                    prompt=current_prompt,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": response_model.__name__, "schema": schema, "strict": True},
                    },
                )

                content = response.choices[0].message.content
                if not content or not content.strip():
                    raise LLMProviderError("LLM returned an empty structured response.")

                result = (
                    response_model.model_validate(content)
                    if isinstance(content, dict)
                    else response_model.model_validate_json(content)
                )

                self._record_success_metrics(provider, model, usage, latency_ms)

                log_info(
                    "llm.structured.request.completed",
                    provider=provider,
                    model=model,
                    attempt=attempt,
                    latency_ms=latency_ms,
                    validation_status="success",
                )
                return result

            except (ValidationError, *self.LITELLM_EXCEPTIONS, Exception) as exc:
                last_error = exc
                is_val = isinstance(exc, ValidationError)
                record_validation_failure(provider, model)

                if attempt < max_attempts:
                    record_retry(provider, model, "validation_failure" if is_val else "provider_failure")

                log_warning(
                    f"llm.structured.{'validation' if is_val else 'request'}.failed",
                    provider=provider,
                    model=model,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error=str(exc),
                )
                if attempt >= max_attempts:
                    break
                time.sleep(settings.ai.retry_backoff * attempt)

        log_error("llm.structured.request.exhausted", provider=provider, model=model, max_attempts=max_attempts,
                  error=str(last_error))
        raise LLMProviderError(f"LiteLLM structured output failed: {last_error}")

    def _execute_completion(self, prompt: str, response_format: dict | None = None) -> str:
        provider, model = settings.ai.llm_provider, settings.ai.llm_model
        start_time = time.perf_counter()

        try:
            kwargs = {
                "model": model,
                "api_key": settings.ai.model_api_key,
                "timeout": settings.ai.timeout,
                "temperature": settings.ai.temperature if not response_format else 0,
                "max_tokens": settings.ai.max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
            if response_format:
                kwargs["response_format"] = response_format

            response = completion(**kwargs)
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            content = response.choices[0].message.content

            if not content or not content.strip():
                raise LLMProviderError("LLM returned an empty response.")
            return content

        except self.LITELLM_EXCEPTIONS as e:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            log_error("llm.chat.request.failed", provider=provider, model=model, latency_ms=latency_ms, error=str(e))
            raise LLMProviderError(f"LiteLLM provider error: {e}") from e

    def _execute_call(self, prompt: str, response_format: dict):
        start_time = time.perf_counter()
        response = completion(
            model=settings.ai.llm_model,
            api_key=settings.ai.model_api_key,
            timeout=settings.ai.timeout,
            temperature=0,
            max_tokens=settings.ai.max_tokens,
            messages=[{"role": "user", "content": prompt}],
            response_format=response_format,
        )
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        usage = self._extract_usage(response)
        return response, latency_ms, usage

    @staticmethod
    def _record_success_metrics(provider: str, model: str, usage: dict | None, latency_ms: float):
        estimated_cost = estimate_llm_cost_usd(model, usage, model_costs=model_cost)
        record_llm_success(provider, model, latency_ms)
        record_token_usage(provider, model, usage)
        record_cost(provider, model, estimated_cost)

    @staticmethod
    def _build_structured_prompt(prompt: str, last_error: Exception | None) -> str:
        if not last_error:
            return prompt
        return f"{prompt}\n\nPrevious response failed schema validation. Error: {last_error}. Return valid JSON only."

    @staticmethod
    def _extract_usage(response) -> dict[str, int] | None:
        usage = getattr(response, "usage", None)
        if not usage:
            return None
        keys = ("prompt_tokens", "completion_tokens", "total_tokens")
        return {k: (usage.get(k) if isinstance(usage, dict) else getattr(usage, k, None)) for k in keys}