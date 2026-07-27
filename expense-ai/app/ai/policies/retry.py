from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential, RetryCallState
from app.ai.models import ExecutionContext, ProviderResponse
from app.ai.policies.base import ExecutionHandler, Policy
from app.config import settings
from app.exceptions import LLMProviderError
from app.observability.logging import log_warning
from app.observability.metrics import record_retry


class RetryPolicy(Policy):
    priority: int = 30

    def _before_sleep(self, context: ExecutionContext):
        def callback(retry_state: RetryCallState) -> None:
            exception = retry_state.outcome.exception() if retry_state.outcome else None
            provider = context.provider

            record_retry(
                provider=provider.name ,
                model=provider.model,
                reason=type(exception).__name__ if exception else "unknown",
            )
            log_warning(
                "runtime.retry",
                execution_id=str(context.execution_id),
                attempt=context.attempt,
                next_attempt=context.attempt + 1,
                error=str(exception) if exception else None,
            )

        return callback

    def execute(self, context: ExecutionContext, next_handler: ExecutionHandler) -> ProviderResponse:
        rt_s = settings.runtime

        retryer = Retrying(
            stop=stop_after_attempt(rt_s.max_retries + 1),
            wait=wait_exponential(multiplier=rt_s.retry_backoff, min=1, max=3),
            retry=retry_if_exception_type(LLMProviderError),
            reraise=True,
            before_sleep=self._before_sleep(context),
        )

        for attempt in retryer:
            with attempt:
                context.attempt += 1
                return next_handler()