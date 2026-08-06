"""
Layer 1 (app-level masking, primary control) and Layer 4 (logging filter,
safety net for logs) of the PII redaction plan in
`docs/SECURITY-PLAN.md` Section 2.1. Layer 2 (Collector `redaction`
processor) lives in `collector/otel-collector-config*.yaml` - config, not
code, but designed to share the same pattern set as this file (see the
comment above `_PATTERNS` below). Layer 3 (litellm/Presidio, masking what
actually reaches OpenRouter) stays deferred - Phase 3, per confirmed scope
in SECURITY-PLAN.md Section 6.1 - but this file is written so that landing
it later is a one-class addition, not a rewrite (see `PIIDetector` below).

Cost: benchmarked in SECURITY-PLAN.md Section 2.3 at ~25us-800us per call
depending on message length - under 1ms even at the worst case (a maxed-out
4000-character `/chat` message). Where that cost lands is a deliberate
choice, not an accident: `RedactingSpanExporter` defers it to
`BatchSpanProcessor`'s background export thread (verified against the SDK
source in an earlier session: `BatchSpanProcessor.on_end()` only enqueues
the span reference and returns immediately - the real `exporter.export()`
call happens later, off the request path), so this adds zero `/chat`
latency regardless of traffic volume. The logging filter (Layer 4) is the
one place this cost is paid inline - logging itself is synchronous in this
codebase (`logging.basicConfig`'s default `StreamHandler`), and log volume
here is operational messages, not per-request user content, so the ~1ms
worst case is not on the hot path in practice.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from re import Pattern
from typing import Protocol

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult


@dataclass(frozen=True)
class PIIMatch:
    """A single detected span of text, in `text[start:end]` coordinates."""

    start: int
    end: int
    entity_type: str


class PIIDetector(Protocol):
    """
    The seam Presidio (Layer 3 / Phase 3) plugs into later, per
    SECURITY-PLAN.md 6.1: "Build `redact()` as regex-based... but behind
    a small `PIIDetector` protocol/interface... so a `PresidioDetector`
    implementing the same interface can be dropped in later without
    touching any call site." `redact()` below only ever calls `.detect()`
    - it has no idea whether the implementation is regex or an NER model.

    To add Presidio later: implement a class with this method wrapping
    `presidio_analyzer.AnalyzerEngine().analyze(text, language="en")`,
    mapping its `RecognizerResult` list to `PIIMatch` (same `start`/`end`/
    `entity_type` shape - Presidio's results already look almost exactly
    like this). Then change `get_pii_detector()` below to return it
    (behind a config flag, e.g. `PII_DETECTOR=presidio`, so this stays an
    opt-in swap). Nothing in `RedactingSpanExporter`, `PIIRedactionLogFilter`,
    or `set_llm_content_attributes` would need to change.
    """

    def detect(self, text: str) -> list[PIIMatch]: ...


# The 6 pattern classes benchmarked in docs/SECURITY-PLAN.md Section 2.3.
# Mirrored (not imported - the Collector process can't import this Python
# module) into collector/otel-collector-config.yaml's `redaction` processor
# `blocked_values`. RE2 (the Collector's regex engine) doesn't support
# lookaround, and neither do these patterns, so the two stay equivalent -
# if you change one, change the other.
#
# API_KEY is deliberately prefix-based (sk-..., AKIA..., ghp_..., xox...)
# rather than a bare "long alphanumeric run" pattern: this app's own
# session IDs and trace IDs are also long alphanumeric/hex strings (UUIDs),
# and a generic length-based pattern would false-positive-redact those,
# which is exactly the "aggressive scrubbing kills debuggability" tradeoff
# SECURITY-PLAN.md 2.1 warns about. Real API keys are also never attached
# to spans in this codebase in the first place (app/security/auth.py only
# ever exposes `Principal.key_id`, a last-4-chars-only value) - this
# pattern exists for defense in depth against a future mistake, not
# because it's needed today.
_PATTERNS: dict[str, Pattern[str]] = {
    "EMAIL": re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}"),
    "PHONE": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "CREDIT_CARD": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "API_KEY": re.compile(
        r"\b(?:sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|xox[baprs]-[A-Za-z0-9-]{10,})\b"
    ),
    "IPV4": re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"),
}


class RegexPIIDetector:
    """
    Default (and, per confirmed scope in SECURITY-PLAN.md 6.1, only-
    shipped-today) detector. Fast, zero new dependencies, catches
    structured PII (the patterns above). Misses unstructured PII - person
    names, street addresses, anything with no fixed shape - by design:
    that's a different *class* of problem (NER, not pattern matching),
    which is exactly Presidio's value proposition and exactly why it's
    slower (see SECURITY-PLAN.md 2.3's cost comparison).
    """

    def detect(self, text: str) -> list[PIIMatch]:
        matches: list[PIIMatch] = []
        for entity_type, pattern in _PATTERNS.items():
            for m in pattern.finditer(text):
                matches.append(PIIMatch(start=m.start(), end=m.end(), entity_type=entity_type))
        return matches


_default_detector = RegexPIIDetector()


def get_pii_detector() -> PIIDetector:
    """
    Single seam for swapping detectors. Today this always returns the
    regex detector - Presidio is Phase 3, deferred pending a concrete
    need (SECURITY-PLAN.md 6.1). When that need shows up, this is the
    only function that needs to change (see `PIIDetector` docstring).
    """
    return _default_detector


def redact(text: str | None, detector: PIIDetector | None = None) -> str | None:
    """
    Field-level redaction (SECURITY-PLAN.md 2.1): replaces only the
    matched substring with a `[ENTITY_TYPE]` placeholder, not the whole
    string - a trace with `session: [EMAIL] asked about refunds` is still
    useful for debugging; one that reads `[REDACTED]` is not. This is the
    specific tradeoff Langfuse's own PII guidance calls out.
    """
    if not text:
        return text
    detector = detector or get_pii_detector()
    matches = detector.detect(text)
    if not matches:
        return text

    # Merge overlapping/adjacent matches (different patterns can match the
    # same span, e.g. a phone-shaped run inside a longer digit sequence),
    # then apply replacements back-to-front so earlier substitutions don't
    # shift the offsets later ones were computed against.
    ordered = sorted(matches, key=lambda m: m.start)
    merged: list[PIIMatch] = []
    for m in ordered:
        if merged and m.start < merged[-1].end:
            if m.end > merged[-1].end:
                merged[-1] = PIIMatch(merged[-1].start, m.end, merged[-1].entity_type)
            continue
        merged.append(m)

    out = text
    for m in reversed(merged):
        out = f"{out[: m.start]}[{m.entity_type}]{out[m.end :]}"
    return out


# ------------------------------------------------------------- Layer 4 --
class PIIRedactionLogFilter(logging.Filter):
    """
    Registered on the root logger in `app/main.py`. Runs `redact()` over
    every formatted log message before emission, so a future
    `logger.debug(f"user said: {message}")` - added during someone's
    late-night debugging session, and which technically shouldn't exist
    in the first place - doesn't ship raw PII to stdout/log aggregators.
    Safety net (Layer 4): the primary control is Layer 1 below; this
    exists for the same "defense in depth, one control can always be
    bypassed" reasoning as Layer 2.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            # getMessage() resolves `record.msg % record.args` into the
            # final string. Writing that back to `record.msg` and clearing
            # `args` means downstream formatters see the (now redacted)
            # literal text instead of re-attempting `%`-substitution.
            record.msg = redact(record.getMessage())
            record.args = ()
        except Exception:  # noqa: BLE001, S110 - see below
            # Deliberately silent, not just lazy: this filter runs inside
            # the logging system itself, so logging *this* exception
            # through the same logger would risk feeding back into the
            # thing that just failed (recursive/duplicate log records at
            # best, infinite recursion at worst if the failure is
            # systemic). A malformed log record failing to redact is a
            # bug worth catching in tests (see tests/test_redaction.py::
            # test_log_filter_never_raises_on_bad_input), not something
            # this filter can safely surface at runtime.
            pass
        return True


# ------------------------------------------------------------- Layer 1 --
class RedactingSpanExporter(SpanExporter):
    """
    Wraps any `SpanExporter` and redacts every string-valued span
    attribute before the wrapped exporter (OTLP/HTTP, console, whichever
    `OBSERVABILITY_PROVIDER` is active) ever sees it. This is the primary
    control - broader than just the not-yet-used `set_llm_content_attributes`
    helper below, because this app doesn't validate the shape of every
    string that ends up on a span (`app.session_id` is user-suppliable
    with no format constraint - see `app/api/routes.py::ChatRequest` - so
    a user could put an email address in it as their own tracking
    convention, and that's exactly the kind of accidental leak this layer
    exists to catch without requiring every call site to remember to
    redact).

    Deliberately a `SpanExporter` wrapper, not a `SpanProcessor`: verified
    against the installed SDK's source (`BatchSpanProcessor.on_end()`
    only enqueues the span reference and returns immediately - the real
    `export()` call happens later, on the processor's own background
    thread). Wrapping the exporter instead of adding a processor means
    this cost is paid entirely off the `/chat` request path, regardless
    of traffic volume. See `docs/SECURITY-PLAN.md` Section 2.3.

    Implementation note (version-dependent SDK internals, verified against
    opentelemetry-sdk in this session): `ReadableSpan.attributes` is a
    read-only `MappingProxyType` view over `ReadableSpan._attributes`
    (usually a `BoundedAttributes` instance, which raises `TypeError` on
    any attempted in-place mutation once a span is finished/immutable).
    There is no public API for changing a span's attributes post hoc, so
    this replaces the whole `_attributes` reference with a plain `dict`
    instead of mutating in place - confirmed safe:
    `ReadableSpan.dropped_attributes` falls back to `0` for any non-
    `BoundedAttributes` container, and the OTLP encoder only ever calls
    `.items()` on `span.attributes`, which a plain dict supports
    identically.
    """

    def __init__(self, wrapped: SpanExporter, detector: PIIDetector | None = None) -> None:
        self._wrapped = wrapped
        self._detector = detector or get_pii_detector()

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        for span in spans:
            attrs = span.attributes
            if not attrs:
                continue
            redacted = {}
            changed = False
            for key, value in attrs.items():
                if isinstance(value, str):
                    new_value = redact(value, self._detector)
                    if new_value != value:
                        changed = True
                    redacted[key] = new_value
                else:
                    # Non-string attributes (ints, floats, bools, the odd
                    # sequence like gen_ai.response.finish_reasons) pass
                    # through untouched - regex redaction only makes sense
                    # against text.
                    redacted[key] = value
            if changed:
                span._attributes = redacted  # noqa: SLF001 - see class docstring
        return self._wrapped.export(spans)

    def shutdown(self) -> None:
        self._wrapped.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._wrapped.force_flush(timeout_millis)
