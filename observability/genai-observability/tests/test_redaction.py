"""
PII redaction - Layer 1 (RedactingSpanExporter), Layer 4
(PIIRedactionLogFilter), and the shared detect()/redact() plumbing behind
both. Layer 2 (Collector `redaction` processor) is config, not code -
covered separately in tests/test_collector_config.py.
"""
import logging

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.observability.redaction import (
    PIIMatch,
    PIIRedactionLogFilter,
    RedactingSpanExporter,
    RegexPIIDetector,
    redact,
)


# ------------------------------------------------------------ detection --
def test_detects_email():
    matches = RegexPIIDetector().detect("contact ravik775@gmail.com please")
    assert any(m.entity_type == "EMAIL" for m in matches)


def test_detects_phone():
    matches = RegexPIIDetector().detect("call me at 555-123-4567")
    assert any(m.entity_type == "PHONE" for m in matches)


def test_detects_ssn():
    matches = RegexPIIDetector().detect("SSN is 123-45-6789")
    assert any(m.entity_type == "SSN" for m in matches)


def test_detects_credit_card():
    matches = RegexPIIDetector().detect("card 4111 1111 1111 1111 expires soon")
    assert any(m.entity_type == "CREDIT_CARD" for m in matches)


def test_detects_api_key_shaped_tokens():
    matches = RegexPIIDetector().detect("key is sk-abcdefghijklmnopqrstuvwxyz123456")
    assert any(m.entity_type == "API_KEY" for m in matches)


def test_detects_ipv4():
    matches = RegexPIIDetector().detect("connect to 192.168.1.100 now")
    assert any(m.entity_type == "IPV4" for m in matches)


def test_no_false_positive_on_clean_text():
    matches = RegexPIIDetector().detect("the quick brown fox jumps over the lazy dog")
    assert matches == []


def test_does_not_detect_names_or_addresses():
    # Documented limitation (regex has no concept of "is this a name") -
    # this is exactly the gap Presidio (Layer 3, deferred) would close.
    matches = RegexPIIDetector().detect("My name is John Smith and I live in Paris")
    assert matches == []


# ----------------------------------------------------------------- redact --
def test_redact_replaces_only_the_matched_substring():
    out = redact("email me at ravik775@gmail.com about the order")
    assert "ravik775@gmail.com" not in out
    assert "[EMAIL]" in out
    assert "about the order" in out  # surrounding text preserved


def test_redact_handles_multiple_distinct_entities():
    out = redact("email ravik775@gmail.com or call 555-123-4567")
    assert "[EMAIL]" in out
    assert "[PHONE]" in out
    assert "ravik775@gmail.com" not in out
    assert "555-123-4567" not in out


def test_redact_none_returns_none():
    assert redact(None) is None


def test_redact_empty_string_returns_empty_string():
    assert redact("") == ""


def test_redact_clean_text_returned_unchanged():
    text = "everything here is fine"
    assert redact(text) == text


def test_redact_merges_overlapping_matches():
    # A credit-card-shaped digit run inside a longer sequence can also
    # partially match the phone pattern - redact() should not double up
    # or corrupt the output on overlap.
    out = redact("card number 4111111111111111 was charged")
    assert out.count("[") == out.count("]")  # every placeholder is well-formed
    assert "4111111111111111" not in out


def test_redact_with_custom_detector():
    class FixedDetector:
        def detect(self, text):
            return [PIIMatch(start=0, end=5, entity_type="CUSTOM")]

    assert redact("hello world", detector=FixedDetector()) == "[CUSTOM] world"


# --------------------------------------------------- Layer 4: log filter --
def test_log_filter_redacts_formatted_message():
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="user said: %s",
        args=("contact me at ravik775@gmail.com",),
        exc_info=None,
    )
    result = PIIRedactionLogFilter().filter(record)
    assert result is True
    assert "ravik775@gmail.com" not in record.getMessage()
    assert "[EMAIL]" in record.getMessage()


def test_log_filter_never_raises_on_bad_input():
    # A record with no message at all shouldn't crash the filter (and
    # therefore shouldn't crash logging itself).
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg=None, args=None, exc_info=None,
    )
    assert PIIRedactionLogFilter().filter(record) is True


def test_log_filter_leaves_clean_messages_unchanged():
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="Startup complete", args=None, exc_info=None,
    )
    PIIRedactionLogFilter().filter(record)
    assert record.getMessage() == "Startup complete"


# ------------------------------------------------- Layer 1: span export --
def _make_provider(exporter):
    tp = TracerProvider()
    tp.add_span_processor(SimpleSpanProcessor(exporter))
    return tp


def test_redacting_span_exporter_redacts_string_attributes():
    inner = InMemorySpanExporter()
    wrapped = RedactingSpanExporter(inner)
    tp = _make_provider(wrapped)
    tracer = tp.get_tracer("test")

    with tracer.start_as_current_span("s") as span:
        span.set_attribute("app.session_id", "ravik775@gmail.com")
        span.set_attribute("app.request.message_length", 42)

    spans = inner.get_finished_spans()
    assert len(spans) == 1
    attrs = spans[0].attributes
    assert attrs["app.session_id"] == "[EMAIL]"
    assert attrs["app.request.message_length"] == 42  # non-string untouched


def test_redacting_span_exporter_leaves_clean_spans_unchanged():
    inner = InMemorySpanExporter()
    wrapped = RedactingSpanExporter(inner)
    tp = _make_provider(wrapped)
    tracer = tp.get_tracer("test")

    with tracer.start_as_current_span("s") as span:
        span.set_attribute("app.endpoint", "/chat")

    attrs = inner.get_finished_spans()[0].attributes
    assert attrs["app.endpoint"] == "/chat"


def test_redacting_span_exporter_delegates_to_wrapped_exporter():
    inner = InMemorySpanExporter()
    wrapped = RedactingSpanExporter(inner)
    tp = _make_provider(wrapped)
    tracer = tp.get_tracer("test")

    with tracer.start_as_current_span("s1"):
        pass
    with tracer.start_as_current_span("s2"):
        pass

    assert len(inner.get_finished_spans()) == 2


def test_redacting_span_exporter_shutdown_and_force_flush_delegate():
    inner = InMemorySpanExporter()
    wrapped = RedactingSpanExporter(inner)

    assert wrapped.force_flush() is True
    wrapped.shutdown()  # should not raise; InMemorySpanExporter.shutdown() is a no-op
