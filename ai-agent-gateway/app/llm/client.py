import logging
from abc import ABC, abstractmethod
from typing import Any

import litellm
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class LLMClient(ABC):
    @abstractmethod
    def generate(self, messages: list[dict[str, str]], model: str | None = None) -> str:
        raise NotImplementedError


class LiteLLMClient(LLMClient):
    def __init__(self) -> None:
        self.settings = get_settings()
        litellm.drop_params = True

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=4))
    def generate(self, messages: list[dict[str, str]], model: str | None = None) -> str:
        selected_model = model or self.settings.default_model
        kwargs: dict[str, Any] = {
            'model': selected_model,
            'messages': messages,
            'temperature': 0.1,
            'max_tokens': 500,
            'timeout': self.settings.request_timeout_seconds,
        }
        if self.settings.litellm_api_base:
            kwargs['api_base'] = self.settings.litellm_api_base
        try:
            response = litellm.completion(**kwargs)
            return response.choices[0].message.content or ''
        except Exception:
            logger.exception('LLM call failed for model=%s', selected_model)
            if selected_model != self.settings.fallback_model:
                response = litellm.completion(
                    model=self.settings.fallback_model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=500,
                    timeout=self.settings.request_timeout_seconds,
                )
                return response.choices[0].message.content or ''
            raise
