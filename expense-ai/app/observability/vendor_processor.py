from typing import Optional
from opentelemetry.context import Context
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor

class DynamicVendorAttributeProcessor(SpanProcessor):
    """
    OpenTelemetry SpanProcessor that dynamically adds vendor-specific prefixes
    (e.g., langsmith.metadata. or langfuse.trace.metadata.) to custom attributes
    before spans are exported.
    """
    def __init__(self, target_vendor: str = "langsmith"):
        self.target_vendor = target_vendor.lower()

    def on_start(self, span: Span, parent_context: Optional[Context] = None) -> None:
        pass

    def on_end(self, span: ReadableSpan) -> None:
        if not span.attributes:
            return

        original_attributes = dict(span.attributes)

        for key, value in original_attributes.items():
            if key.startswith("expense.") or key.startswith("ai."):
                clean_key = key.split(".", 1)[-1]

                if self.target_vendor == "langsmith":
                    target_key = f"langsmith.metadata.{clean_key}"
                elif self.target_vendor == "langfuse":
                    target_key = f"langfuse.trace.metadata.{clean_key}"
                else:
                    target_key = None

                # Safely write to underlying BoundedAttributes internal dict
                if target_key and hasattr(span, "_attributes") and hasattr(span._attributes, "_dict"):
                    span._attributes._dict[target_key] = value