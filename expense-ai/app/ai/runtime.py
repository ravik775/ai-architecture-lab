from abc import ABC

from litellm import model_cost

from app.ai.models import ExecutionContext
from app.ai.models import AIRequest, ResponseModel
from app.ai.pipeline import Pipeline
from app.ai.policies.FallbackPolicy import FallbackPolicy
from app.ai.policies.circuit_breaker import CircuitBreakerPolicy, CircuitBreakerRegistry
from app.ai.policies.logging import ObservabilityPolicy
from app.ai.policies.retry import RetryPolicy
from app.ai.policies.timeout_policy import TimeoutPolicy
from app.ai.providers import ProviderRegistry
from app.llm.base import LLMService
from app.observability.cost import estimate_llm_cost_usd
from app.observability.logging import log_error, log_info
from app.observability.metrics import record_cost, record_llm_success, record_token_usage


class AIRuntime:

    def __init__(self, llm_service: LLMService):
        self._pipeline = Pipeline([
                ObservabilityPolicy(),
                FallbackPolicy(),
                RetryPolicy(),
                CircuitBreakerPolicy(),
                TimeoutPolicy(),
            ])
        self.llm_service = llm_service

    def invoke(self, request: AIRequest, response_model: type[ResponseModel]) -> ResponseModel:
        if not request.prompt:
            raise ValueError("Prompt is required.")

        context = ExecutionContext()
        log_info("runtime.execution.started", execution_id=str(context.execution_id))

        try:
            handler = lambda: self.llm_service.invoke(context, request, response_model )
            provider_response = self._pipeline.execute(context, handler)
            estimated_cost = estimate_llm_cost_usd(provider_response.model, provider_response.usage, model_cost)

            record_llm_success(provider_response.provider, provider_response.model, provider_response.latency_ms,)
            record_token_usage(provider_response.provider, provider_response.model, provider_response.usage,)
            record_cost(provider_response.provider, provider_response.model, estimated_cost,)

            log_info("runtime.execution.completed", execution_id=str(context.execution_id),
                     provider=provider_response.provider, model=provider_response.model,latency_ms=provider_response.latency_ms,)

            return provider_response.content
        except Exception as ex:
            log_error("runtime.execution.failed", execution_id=str(context.execution_id), error=str(ex))
            raise


