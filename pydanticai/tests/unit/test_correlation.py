from __future__ import annotations

import pytest
from opentelemetry import baggage
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import app.observability.correlation as correlation_module
from app.observability.context import correlation_id_var
from app.observability.correlation import correlation_scope, new_correlation_id
from app.observability.sampling import FORCE_TRACE_AUTH_BAGGAGE_KEY, FORCE_TRACE_BAGGAGE_KEY


def test_new_correlation_id_generates_unique_values():
    a, b = new_correlation_id(), new_correlation_id()
    assert a != b
    assert len(a) == 36  # UUID4 string form


@pytest.fixture()
def in_memory_exporter(monkeypatch):
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(correlation_module, "tracer", provider.get_tracer("test"))
    return exporter


def test_correlation_scope_sets_and_resets_contextvar(in_memory_exporter):
    assert correlation_id_var.get() == ""
    with correlation_scope("my-friendly-id", "ui.test_op"):
        assert correlation_id_var.get() == "my-friendly-id"
    assert correlation_id_var.get() == ""


def test_correlation_scope_falls_back_to_generated_id_when_blank(in_memory_exporter):
    with correlation_scope("", "ui.test_op"):
        value = correlation_id_var.get()
        assert value != ""
        assert len(value) == 36


def test_correlation_scope_tags_span_with_correlation_id(in_memory_exporter):
    with correlation_scope("my-friendly-id", "ui.test_op"):
        pass

    spans = in_memory_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "ui.test_op"
    assert spans[0].attributes["correlation_id"] == "my-friendly-id"


def test_correlation_scope_resets_even_on_exception(in_memory_exporter):
    with pytest.raises(RuntimeError):
        with correlation_scope("my-friendly-id", "ui.test_op"):
            raise RuntimeError("boom")
    assert correlation_id_var.get() == ""


def test_correlation_scope_without_force_trace_never_sets_that_baggage(in_memory_exporter):
    with correlation_scope("cid", "ui.test_op"):
        assert baggage.get_baggage(FORCE_TRACE_BAGGAGE_KEY) is None
        assert baggage.get_baggage(FORCE_TRACE_AUTH_BAGGAGE_KEY) is None


def test_correlation_scope_force_trace_without_token_is_a_no_op(in_memory_exporter):
    """Same guard `_trace_kwargs` applies UI-side (see app/ui/pages.py) -
    correlation_scope enforces it independently too, so a caller can't
    force-trace by passing force_trace=True alone."""
    with correlation_scope("cid", "ui.test_op", force_trace=True, auth_token=None):
        assert baggage.get_baggage(FORCE_TRACE_BAGGAGE_KEY) is None
        assert baggage.get_baggage(FORCE_TRACE_AUTH_BAGGAGE_KEY) is None


def test_correlation_scope_sets_force_trace_baggage_visible_at_span_creation(in_memory_exporter, monkeypatch):
    """Can't intercept should_sample() directly here (this fixture's
    TracerProvider has no custom Sampler) - what matters is that the
    force_trace/auth_token baggage is present on the context at the exact
    moment the span is created, since that's the only hook point a real
    Sampler gets (see sampling.py). Verified by spying on
    start_as_current_span and snapshotting baggage before delegating."""
    captured = {}
    original_start = correlation_module.tracer.start_as_current_span

    def spy_start(name):
        captured["force_trace"] = baggage.get_baggage(FORCE_TRACE_BAGGAGE_KEY)
        captured["auth_token"] = baggage.get_baggage(FORCE_TRACE_AUTH_BAGGAGE_KEY)
        return original_start(name)

    monkeypatch.setattr(correlation_module.tracer, "start_as_current_span", spy_start)

    with correlation_scope("cid", "ui.test_op", force_trace=True, auth_token="secret-jwt"):
        pass

    assert captured["force_trace"] == "true"
    assert captured["auth_token"] == "secret-jwt"


def test_correlation_scope_scrubs_auth_token_once_span_exists(in_memory_exporter):
    """The security-critical behavior: once the span (and sampling
    decision) exists, `auth_token` must not still be attached to the
    context - otherwise it would ride along into this action's own
    outgoing httpx calls (Open-Meteo/LiteLLM) via the same baggage
    propagator. `correlation_id` and `force_trace` (not a credential) are
    fine to leave in place."""
    captured = {}
    with correlation_scope("cid", "ui.test_op", force_trace=True, auth_token="secret-jwt"):
        captured["auth_token"] = baggage.get_baggage(FORCE_TRACE_AUTH_BAGGAGE_KEY)
        captured["force_trace"] = baggage.get_baggage(FORCE_TRACE_BAGGAGE_KEY)
        captured["correlation_id"] = baggage.get_baggage("correlation_id")

    assert captured["auth_token"] is None
    assert captured["force_trace"] == "true"
    assert captured["correlation_id"] == "cid"


def test_correlation_scope_leaves_no_baggage_after_exit(in_memory_exporter):
    with correlation_scope("cid", "ui.test_op", force_trace=True, auth_token="secret-jwt"):
        pass

    assert baggage.get_baggage(FORCE_TRACE_AUTH_BAGGAGE_KEY) is None
    assert baggage.get_baggage(FORCE_TRACE_BAGGAGE_KEY) is None
    assert baggage.get_baggage("correlation_id") is None
