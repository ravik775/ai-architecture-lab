from app.ai.models import ExecutionContext
from app.ai.models import AIRequest, TResponse
from app.ai.pipeline_factory import PipelineFactory
from app.llm.base import LLMService
from opentelemetry import trace

from app.llm.response_parser import ResponseParser

tracer = trace.get_tracer("expense-ai")


class AIRuntime:

    def __init__(self, llm_service: LLMService):
        self._pipeline = PipelineFactory.build()
        self.llm_service = llm_service
        self._response_parser = ResponseParser()

    def invoke(self, request: AIRequest, response_model: type[TResponse]) -> TResponse:
        context = ExecutionContext(request=request, response_model=response_model )
        with tracer.start_as_current_span("ai.runtime.invoke") as span:
            span.set_attribute("ai.execution_id", str(context.execution_id))
            span.set_attribute("ai.response_model", response_model.__name__)
            handler = lambda: self.llm_service.invoke(context, context.request)
            provider_response = self._pipeline.execute(context, handler)
            span.set_attribute("llm.provider", provider_response.provider)
            span.set_attribute("llm.model", provider_response.model)
            span.set_attribute("llm.latency_ms", provider_response.latency_ms)
            return self._response_parser.parse(provider_response, response_model)

