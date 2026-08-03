import hashlib
import logging
from typing import Optional
from cachetools import TTLCache
from opentelemetry import trace

from app.ai.models import ExecutionContext, ProviderResponse, TResponse
from app.ai.policies.base import Policy, ExecutionHandler
from app.config import settings

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("expense-ai")


class CachePolicy(Policy):
    name: str = "cache"
    priority: int = 20
    _shared_cache: Optional[TTLCache] = None

    def __init__(self) -> None:
        super().__init__()
        # Safely extract configuration from settings
        cache_config = getattr(settings, "pipeline", {})
        if isinstance(cache_config, dict):
            cache_settings = cache_config.get("cache", {})
        else:
            cache_settings = getattr(cache_config, "cache", {})

        if isinstance(cache_settings, dict):
            self.enabled: bool = cache_settings.get("enabled", True)
            ttl_seconds: int = cache_settings.get("ttl_seconds", 3600)
            max_size: int = cache_settings.get("max_size", 1024)
        else:
            self.enabled = getattr(cache_settings, "enabled", True)
            ttl_seconds = getattr(cache_settings, "ttl_seconds", 3600)
            max_size = getattr(cache_settings, "max_size", 1024)

        # Singleton pattern for shared TTLCache
        if CachePolicy._shared_cache is None:
            CachePolicy._shared_cache = TTLCache(maxsize=max_size, ttl=ttl_seconds)

        self._cache: TTLCache = CachePolicy._shared_cache

    def _generate_key(self, context: ExecutionContext) -> str:
        """Generates a SHA256 cache key based on provider, model, and prompt."""
        provider = getattr(context.provider, "name", "")
        model = getattr(context.provider, "model", "")
        prompt = getattr(context.request, "prompt", "")
        raw_string = f"{provider}:{model}:{prompt}"
        return hashlib.sha256(raw_string.encode("utf-8")).hexdigest()

    def execute(
        self, context: ExecutionContext, next_handler: ExecutionHandler
    ) -> ProviderResponse[TResponse]:
        if not self.enabled:
            logger.debug("CachePolicy disabled, proceeding to next handler.")
            return next_handler()  # FIXED: Called without arguments

        cache_key = self._generate_key(context)

        with tracer.start_as_current_span("expense.cache.lookup") as span:
            span.set_attribute("expense.cache.cache_key", cache_key)

            # Check for Cache Hit
            if cache_key in self._cache:
                logger.info("Cache hit", extra={"cache_key": cache_key, "policy": self.name})
                span.set_attribute("expense.cache.hit", True)
                return self._cache[cache_key]

            # Cache Miss
            logger.info("Cache miss", extra={"policy": self.name, "cache_key": cache_key})
            span.set_attribute("expense.cache.hit", False)

            # Invoke next policy in the chain
            response = next_handler()  # FIXED: Called without arguments

            # Store in cache on success
            if response is not None:
                self._cache[cache_key] = response
                logger.debug("Response cached successfully", extra={"cache_key": cache_key})

            return response