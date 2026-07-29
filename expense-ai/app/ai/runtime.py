from app.ai.models import ExecutionContext
from app.ai.models import AIRequest, ResponseModel
from app.ai.pipeline_factory import PipelineFactory
from app.llm.base import LLMService
from opentelemetry import trace

tracer = trace.get_tracer("expense-ai")

class AIRuntime:

    def __init__(self, llm_service: LLMService):
        self._pipeline = PipelineFactory.build()
        self.llm_service = llm_service

    def invoke(self, request: AIRequest, response_model: type[ResponseModel]) -> ResponseModel:
        if not request.prompt:
            raise ValueError("Prompt is required.")
        context = ExecutionContext(prompt=request.prompt)
        with tracer.start_as_current_span("ai.runtime.invoke") as span:
            span.set_attribute("ai.execution_id", str(context.execution_id))
            span.set_attribute("ai.response_model", response_model.__name__)
            handler = lambda: self.llm_service.invoke(context, request, response_model )
            provider_response = self._pipeline.execute(context, handler)
            span.set_attribute("llm.provider", provider_response.provider)
            span.set_attribute("llm.model", provider_response.model)
            span.set_attribute("llm.latency_ms", provider_response.latency_ms)
            return provider_response.content


