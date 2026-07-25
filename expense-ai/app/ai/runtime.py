from litellm import model_cost

from app.ai.execution_context import ExecutionContext
from app.ai.models import AIRequest
from app.config import settings
from app.llm.base import LLMService, T
from app.observability.cost import estimate_llm_cost_usd
from app.observability.logging import log_error, log_info
from app.observability.metrics import record_cost, record_llm_success, record_token_usage


class AIRuntime:

    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service

    def invoke(self, request: AIRequest, response_model: type[T]) -> T:
        if not request.prompt:
            raise ValueError("Prompt is required.")

        context = ExecutionContext(provider=settings.ai.llm_provider, model=settings.ai.llm_model)
        log_info("runtime.execution.started", execution_id=str(context.execution_id),
            provider=context.provider, model=context.model)

        try:
            provider_response = self.llm_service.invoke(request, response_model)
            estimated_cost = estimate_llm_cost_usd(provider_response.model, provider_response.usage,
                                                   model_costs=model_cost )

            record_llm_success(provider_response.provider, provider_response.model, provider_response.latency_ms,)
            record_token_usage(provider_response.provider, provider_response.model, provider_response.usage,)
            record_cost(provider_response.provider, provider_response.model, estimated_cost,)

            log_info("runtime.execution.completed", execution_id=str(context.execution_id),
                     provider=provider_response.provider, model=provider_response.model,latency_ms=provider_response.latency_ms,)

            return provider_response.content
        except Exception as ex:
            log_error("runtime.execution.failed", execution_id=str(context.execution_id),
                      provider=context.provider, model=context.model, error=str(ex))
            raise