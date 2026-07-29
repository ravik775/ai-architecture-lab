from threading import Lock

from pybreaker import CircuitBreaker

from app.ai.models import ExecutionContext
from app.ai.policies.base import Policy, ExecutionHandler
from app.config import settings


class CircuitBreakerRegistry:
    """
    Maintains one CircuitBreaker per provider.
    """
    _breakers: dict[str, CircuitBreaker] = {}
    _lock = Lock()

    @classmethod
    def get_breaker(cls, provider_name: str) -> CircuitBreaker:
        breaker = cls._breakers.get(provider_name)
        if breaker is not None:
            return breaker

        with cls._lock:
            breaker = cls._breakers.get(provider_name)
            if breaker is None:
                cb = settings.circuit_breaker
                breaker = CircuitBreaker(
                    fail_max=cb.failure_threshold,
                    reset_timeout=cb.reset_timeout,
                    success_threshold=cb.success_threshold,
                )
                cls._breakers[provider_name] = breaker

        return breaker

    @classmethod
    def providers(cls) -> tuple[str, ...]:
        return tuple(cls._breakers.keys())

    @classmethod
    def contains(cls, provider_name: str) -> bool:
        return provider_name in cls._breakers

class CircuitBreakerPolicy(Policy):

    def execute(self, context: ExecutionContext, next_handler: ExecutionHandler):
        breaker = CircuitBreakerRegistry.get_breaker(context.provider.name)
        return breaker.call(next_handler)