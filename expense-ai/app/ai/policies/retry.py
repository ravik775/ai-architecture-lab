from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential, RetryCallState
from app.ai.models import ExecutionContext
from app.ai.models import ProviderResponse
from app.ai.policies.base import ExecutionHandler, Policy
from app.config import settings
from app.exceptions import LLMProviderError
from app.observability.logging import log_warning


class RetryPolicy(Policy):
    priority: int = 30
    @staticmethod
    def _before_sleep(context: ExecutionContext):
        def callback(retry_state: RetryCallState) -> None:
            exception = retry_state.outcome.exception() if retry_state.outcome else None
            log_warning(
                "runtime.retry",
                execution_id=str(context.execution_id),
                attempt=context.attempt,
                next_attempt=context.attempt + 1,
                error=str(exception) if exception else None,
            )
        return callback

    def execute(self, context: ExecutionContext, next_handler: ExecutionHandler,) -> ProviderResponse:
        rt_s = settings.runtime
        @retry(stop=stop_after_attempt(rt_s.max_retries + 1),
                wait=wait_exponential(multiplier=rt_s.retry_backoff, min=1, max=3),
                retry=retry_if_exception_type(LLMProviderError,),
                reraise=True,
                before_sleep=self._before_sleep(context),
        )
        def execute_with_retry():
            context.attempt += 1
            return next_handler()

        return execute_with_retry()