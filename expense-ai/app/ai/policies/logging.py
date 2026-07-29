import time

from litellm import model_cost

from app.ai.models import ExecutionContext, ProviderResponse
from app.ai.policies.base import ExecutionHandler, Policy
from app.observability.cost import estimate_llm_cost_usd
from app.observability.logging import log_error, log_info
from app.observability.metrics import (
    record_cost,
    record_llm_success,
    record_token_usage,
)


class ObservabilityPolicy(Policy):
    """
    Handles runtime observability.

    Responsibilities:
      - Logging
      - Metrics
      - Cost calculation
      - Tracing (future)
    """
    priority: int = 10

    def execute(self,  context: ExecutionContext, next_handler: ExecutionHandler,) -> ProviderResponse:
        started = time.perf_counter()
        log_info("runtime.execution.started", execution_id=str(context.execution_id),)
        try:
            result = next_handler()
            execution_ms = round( (time.perf_counter() - started) * 1000, 2, )
            self._record_metrics(result)
            self._record_cost(result)
            self._record_trace(context, result, execution_ms)
            log_info("runtime.execution.completed", execution_id=str(context.execution_id),
                provider=result.provider, model=result.model, execution_ms=execution_ms, provider_latency_ms=result.latency_ms,)
            return result
        except Exception as ex:
            execution_ms = round( (time.perf_counter() - started) * 1000, 2, )
            log_error("runtime.execution.failed", execution_id=str(context.execution_id), execution_ms=execution_ms, error=str(ex),)
            raise


    def _record_metrics(self, result: ProviderResponse, ) -> None:
        record_llm_success(result.provider, result.model, result.latency_ms,)
        record_token_usage(result.provider, result.model, result.usage,)

    def _record_cost(self, result: ProviderResponse,) -> None:
        estimated_cost = estimate_llm_cost_usd(result.model,  result.usage, model_costs=model_cost,)
        record_cost( result.provider, result.model, estimated_cost,)

    def _record_trace(self, context: ExecutionContext, result: ProviderResponse, execution_ms: float,) -> None:
        """
        Placeholder.

        Later this will emit OpenTelemetry spans.

        Example attributes:
            execution_id
            provider
            model
            execution_ms
            prompt_tokens
            completion_tokens
            total_tokens
        """
        pass