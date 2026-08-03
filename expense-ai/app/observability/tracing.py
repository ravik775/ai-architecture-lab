from fastapi import FastAPI
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from app.config import settings
from app.observability.vendor_processor import DynamicVendorAttributeProcessor


class TracingConfigurator:
    def __init__(self, app_settings, service_name: str = "expense-ai") -> None:
        self.settings = app_settings
        self.service_name = service_name
        self._configured = False
        self.vendor_target = getattr(self.settings.observability, "vendor_target", "langsmith")

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
        provider = trace.get_tracer_provider()
        provider.add_span_processor(DynamicVendorAttributeProcessor(target_vendor=self.vendor_target))
        if self.settings.observability.console_trace_exporter_enabled:
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        if settings.observability.otlp_exporter_enabled:
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        FastAPIInstrumentor.instrument_app(app)
        self._configured = True
tracing_configurator = TracingConfigurator(settings)