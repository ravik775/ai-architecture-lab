"""X-Force-Trace override sampler - app/observability/sampling.py."""
from opentelemetry import baggage
from opentelemetry import context as context_api
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF, ALWAYS_ON, Decision

from app.observability.sampling import (
    FORCE_TRACE_BAGGAGE_KEY,
    ForceTraceSampler,
    with_baggage_context,
)


def test_delegates_to_wrapped_sampler_when_no_baggage_set():
    sampler = ForceTraceSampler(ALWAYS_OFF)
    result = sampler.should_sample(
        parent_context=context_api.get_current(), trace_id=123, name="test"
    )
    assert result.decision == Decision.DROP  # ALWAYS_OFF's decision, untouched


def test_overrides_to_record_and_sample_when_baggage_set():
    sampler = ForceTraceSampler(ALWAYS_OFF)  # would normally always drop
    ctx = baggage.set_baggage(FORCE_TRACE_BAGGAGE_KEY, "true")
    result = sampler.should_sample(parent_context=ctx, trace_id=123, name="test")
    assert result.decision == Decision.RECORD_AND_SAMPLE


def test_baggage_value_must_be_exactly_true_string():
    sampler = ForceTraceSampler(ALWAYS_OFF)
    ctx = baggage.set_baggage(FORCE_TRACE_BAGGAGE_KEY, "false")
    result = sampler.should_sample(parent_context=ctx, trace_id=123, name="test")
    assert result.decision == Decision.DROP  # not "true" -> falls through to wrapped sampler


def test_always_on_wrapped_sampler_unaffected_either_way():
    sampler = ForceTraceSampler(ALWAYS_ON)
    result = sampler.should_sample(parent_context=context_api.get_current(), trace_id=1, name="t")
    assert result.decision != Decision.DROP


def test_get_description_mentions_wrapped_sampler():
    sampler = ForceTraceSampler(ALWAYS_ON)
    assert "ForceTraceSampler" in sampler.get_description()
    assert "AlwaysOn" in sampler.get_description() or "always_on" in sampler.get_description().lower()


# --------------------------------------------------------- baggage helper --
def test_with_baggage_context_force_false_is_noop():
    ctx = with_baggage_context(force=False)
    assert baggage.get_baggage(FORCE_TRACE_BAGGAGE_KEY, context=ctx) is None


def test_with_baggage_context_force_true_sets_key():
    ctx = with_baggage_context(force=True)
    assert baggage.get_baggage(FORCE_TRACE_BAGGAGE_KEY, context=ctx) == "true"
