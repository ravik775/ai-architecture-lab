"""Settings defaults and validation - app/config.py."""
import pytest
from pydantic import ValidationError

from app.config import ObservabilityProvider, Settings

# test_routes.py sets some of these process-wide via os.environ.setdefault()
# at module import time (needed there because app.main resolves Settings
# once, at import, via a cached get_settings()). pytest imports every test
# module during collection, before any test body runs, so that pollution is
# visible here regardless of file/test order. Settings() reads straight from
# os.environ (unlike the get_settings() singleton), so tests asserting on
# *default* values must explicitly blank these out first rather than relying
# on a clean environment.
_ENV_KEYS_TO_ISOLATE = ("OBSERVABILITY_PROVIDER", "API_KEYS", "TRACE_SAMPLING_RATIO")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in _ENV_KEYS_TO_ISOLATE:
        monkeypatch.delenv(key, raising=False)


def test_defaults_are_sane():
    s = Settings(openrouter_api_key="x")
    assert s.observability_provider == ObservabilityProvider.COLLECTOR
    assert s.trace_sampling_ratio == 1.0
    assert s.otel_tls_enabled is False
    assert s.api_keys == ""
    assert s.health_check_interval_seconds == 2.0
    assert s.health_summary_window_seconds == 60.0


@pytest.mark.parametrize("ratio", [-0.1, 1.1, 2.0])
def test_trace_sampling_ratio_out_of_bounds_rejected(ratio):
    with pytest.raises(ValidationError):
        Settings(openrouter_api_key="x", trace_sampling_ratio=ratio)


@pytest.mark.parametrize("ratio", [0.0, 0.5, 1.0])
def test_trace_sampling_ratio_in_bounds_accepted(ratio):
    s = Settings(openrouter_api_key="x", trace_sampling_ratio=ratio)
    assert s.trace_sampling_ratio == ratio


def test_observability_provider_accepts_all_documented_values():
    for value in ("collector", "langfuse_direct", "langsmith_direct", "console"):
        s = Settings(openrouter_api_key="x", observability_provider=value)
        assert s.observability_provider.value == value


def test_observability_provider_rejects_unknown_value():
    with pytest.raises(ValidationError):
        Settings(openrouter_api_key="x", observability_provider="not-a-real-provider")


def test_api_keys_field_passthrough():
    s = Settings(openrouter_api_key="x", api_keys="k1:chat;k2:chat,force_trace")
    assert s.api_keys == "k1:chat;k2:chat,force_trace"
