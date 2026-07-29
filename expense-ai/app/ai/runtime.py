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
from opentelemetry import trace

tracer = trace.get_tracer("expense-ai")

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
        with tracer.start_as_current_span("ai.runtime.invoke") as span:
            span.set_attribute("ai.execution_id", str(context.execution_id))
            span.set_attribute("ai.response_model", response_model.__name__)
            handler = lambda: self.llm_service.invoke(context, request, response_model )
            provider_response = self._pipeline.execute(context, handler)
            span.set_attribute("llm.provider", provider_response.provider)
            span.set_attribute("llm.model", provider_response.model)
            span.set_attribute("llm.latency_ms", provider_response.latency_ms)
            return provider_response.content


