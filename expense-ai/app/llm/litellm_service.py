import logging
import time
from litellm import completion, exceptions as litellm_exceptions
from app.config import settings
from app.exceptions import LLMProviderError
from app.llm.base import LLMService

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
                api_base=settings.ai.model_base_url,
                timeout=settings.ai.timeout,
                temperature=settings.ai.temperature,
                max_tokens=settings.ai.max_tokens,
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

