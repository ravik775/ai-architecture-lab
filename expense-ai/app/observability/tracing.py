from fastapi import FastAPI
from app.config import settings

class TracingConfigurator:
    def __init__(self, app_settings, service_name: str = "expense-ai") -> None:
        self.settings = app_settings
        self.service_name = service_name
        self._configured = False

    def configure(self, app: FastAPI) -> None:
        if not self.settings.observability.tracing_enabled:
            return

        if self._configured:
            return

        try:
            from opentelemetry import trace
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
        except ImportError:
            return

        resource = Resource.create({"service.name": self.service_name})
        trace.set_tracer_provider(TracerProvider(resource=resource))
        if self.settings.observability.console_trace_exporter_enabled:
            trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

        FastAPIInstrumentor.instrument_app(app)
        self._configured = True

tracing_configurator = TracingConfigurator(settings)
