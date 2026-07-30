import hashlib
import logging
from cachetools import TTLCache
from app.ai.models import ExecutionContext, ProviderResponse, ResponseModel
from app.ai.policies.base import Policy, ExecutionHandler
from app.config import settings

logger = logging.getLogger(__name__)


class CachePolicy(Policy):
    priority = 22
    name = 'cache'
    _shared_cache = None
    def __init__(self):
        cache_config = getattr(settings.pipeline, "cache", {})
        self.enabled = getattr(cache_config, "enabled", True)
        ttl_seconds = getattr(cache_config, "ttl_seconds", 3600)
        max_size = getattr(cache_config, "max_size", 1024)  # Optional: Prevents memory leaks

        # Initialize the shared cache once
        if CachePolicy._shared_cache is None:
            CachePolicy._shared_cache = TTLCache(maxsize=max_size, ttl=ttl_seconds)

        self._cache = CachePolicy._shared_cache

    def _generate_key(self, context: ExecutionContext) -> str:
        """Generates a SHA256 cache key based on provider, model, and prompt."""
        provider = context.provider.name
        model = context.provider.model
        prompt = context.prompt
        raw_string = f"{provider}:{model}:{prompt}"
        return hashlib.sha256(raw_string.encode("utf-8")).hexdigest()

    def execute(self, context: ExecutionContext, next_handler: ExecutionHandler) -> ProviderResponse[ResponseModel]:
        if not self.enabled:
            return next_handler()

        cache_key = self._generate_key(context)

        # Check for Cache Hit (TTLCache automatically evaluates expiration under the hood)
        if cache_key in self._cache:
            logger.info("Cache hit", extra={"cache_key": cache_key, "policy": self.name})
            return self._cache[cache_key]

        # Cache Miss
        logger.info("Cache miss, policy: %s, cache_key: %s", self.name, cache_key)
        response = next_handler()

        # Store in cache (Expiration tracking is handled automatically)
        self._cache[cache_key] = response
        logger.debug("Response cached successfully", extra={"cache_key": cache_key})

        return response