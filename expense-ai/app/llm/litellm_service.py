import logging
import time
from litellm import completion, exceptions as litellm_exceptions
from pydantic import  ValidationError
from app.config import settings
from app.exceptions import LLMProviderError
from app.llm.base import LLMService, T
# Initialize a module-level logger
logger = logging.getLogger(__name__)

class LiteLLMService(LLMService):
    """
       Provider-agnostic implementation backed by LiteLLM.
    """
    def chat(self, prompt: str) -> str:
        provider = settings.ai.llm_provider
        model = settings.ai.llm_model
        logger.info("Preparing LLM request | provider=%s model=%s", provider, model,)
        start_time = time.perf_counter()
        try:
            response = completion(
                model=model,
                api_key=settings.ai.model_api_key,
                #api_base=settings.ai.model_base_url,
                timeout=settings.ai.timeout,
                temperature=settings.ai.temperature,
                max_tokens=settings.ai.max_tokens,
                #reasoning_effort="low",
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            latency = time.perf_counter() - start_time
            content = response.choices[0].message.content
            logger.info(
                f"LLM request succeeded | Provider: {provider} | Model: {model} | Latency: {latency:.4f}s"
            )
            if content is None or not content.strip():
                raise LLMProviderError("LLM returned an empty response." )
            return content
        except (litellm_exceptions.RateLimitError,
                litellm_exceptions.AuthenticationError,
                litellm_exceptions.Timeout,
                litellm_exceptions.APIConnectionError ) as e:
            latency = time.perf_counter() - start_time
            logger.error(
                f"LLM request failed | Provider: {provider} | Model: {model} | Latency: {latency:.4f}s | Error: {e}",
                exc_info=True
            )
            raise LLMProviderError(f"LiteLLM provider error: {e}") from e

    def structured_chat(self, prompt: str, response_model: type[T]) -> T:
        provider = settings.ai.llm_provider
        model = settings.ai.llm_model
        max_attempts = max(1, settings.ai.max_retries + 1)
        schema = response_model.model_json_schema()
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            start_time = time.perf_counter()
            try:
                response = completion(
                    model=model,
                    api_key=settings.ai.model_api_key,
                    timeout=settings.ai.timeout,
                    temperature=0,
                    max_tokens=settings.ai.max_tokens,
                    messages=[
                        {
                            "role": "user",
                            "content": self._build_structured_prompt(prompt, last_error),
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
                latency = time.perf_counter() - start_time
                content = response.choices[0].message.content
                logger.info(
                    "Structured LLM request succeeded | provider=%s model=%s attempt=%s latency=%.4fs",
                    provider,
                    model,
                    attempt,
                    latency,
                )

                if isinstance(content, dict):
                    return response_model.model_validate(content)

                if content is None or not content.strip():
                    raise LLMProviderError("LLM returned an empty structured response.")

                return response_model.model_validate_json(content)

            except ValidationError as exc:
                last_error = exc
                logger.warning(
                    "Structured LLM validation failed | provider=%s model=%s attempt=%s/%s error=%s",
                    provider,
                    model,
                    attempt,
                    max_attempts,
                    exc,
                )
            except (
                litellm_exceptions.RateLimitError,
                litellm_exceptions.AuthenticationError,
                litellm_exceptions.Timeout,
                litellm_exceptions.APIConnectionError,
            ) as exc:
                last_error = exc
                logger.warning(
                    "Structured LLM provider call failed | provider=%s model=%s attempt=%s/%s error=%s",
                    provider,
                    model,
                    attempt,
                    max_attempts,
                    exc,
                    exc_info=True,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Structured LLM request failed | provider=%s model=%s attempt=%s/%s error=%s",
                    provider,
                    model,
                    attempt,
                    max_attempts,
                    exc,
                    exc_info=True,
                )

        raise LLMProviderError(
            f"LiteLLM structured output failed after {max_attempts} attempt(s): {last_error}"
        )

    @staticmethod
    def _build_structured_prompt(prompt: str, last_error: Exception | None) -> str:
        if last_error is None:
            return prompt

        return (
            f"{prompt}\n\n"
            "The previous response did not match the required schema.\n"
            "Retry and return only valid JSON that satisfies the configured response schema.\n"
            f"Validation/provider error: {last_error}"
        )