from pybreaker import CircuitBreakerError
from app.ai.models import ExecutionContext
from app.ai.policies.base import ExecutionHandler, Policy
from app.ai.policies.circuit_breaker import CircuitBreakerRegistry
from app.ai.providers import ProviderRegistry
from app.exceptions import LLMProviderError
from app.observability.logging import log_info, log_warning


class FallbackPolicy(Policy):
    priority = 20

    def execute(self, context: ExecutionContext, next_handler: ExecutionHandler):
        last_exception = None
        for index, provider in enumerate(ProviderRegistry.providers(), start=1):
            breaker = CircuitBreakerRegistry.get_breaker(provider.name)
            if breaker.current_state == "open": # Skip OPEN circuits.
                log_info("runtime.provider.skipped", provider=provider.name, reason="circuit_open")
                continue

            context.provider = provider
            context.provider_index = index
            try:
                log_info("runtime.provider.selected", provider=provider.name)
                return next_handler()
            except CircuitBreakerError as ex: # Breaker opened while executing.
                log_warning("runtime.provider.unavailable", provider=provider.name, error=str(ex) )
                last_exception = ex
            except LLMProviderError as ex: # Provider exhausted retries.
                log_warning("runtime.provider.failed", provider=provider.name, error=str(ex), )
                last_exception = ex
        if last_exception:
            raise last_exception
        raise RuntimeError("No available providers.")