from app.ai.models import ExecutionContext
from app.ai.models import ProviderResponse
from app.ai.policies.base import ExecutionHandler, Policy
from app.ai.utils.timeout import execute_with_timeout
from app.config import settings


class TimeoutPolicy(Policy):
    """
    Enforces the maximum execution time for the downstream
    provider call.
    """
    priority: int = 50
    def execute(self, context: ExecutionContext, next_handler: ExecutionHandler,) -> ProviderResponse:
        return execute_with_timeout(timeout_seconds=settings.runtime.timeout_seconds, func=next_handler,)