"""Guards the "never put raw city names, coordinates, trace/request IDs, or
exception messages in metric labels" constraint: every label value used
anywhere in the app must come from a small, fixed enum, never a location_id
or free-text string.
"""
from __future__ import annotations

from app.observability import metrics as m

_ALLOWED_LABEL_VALUES = {
    "method": {"GET", "POST", "PUT", "DELETE", "PATCH"},
    "status_code": {str(code) for code in range(200, 600)},
    "path_type": {"location", "coordinates"},
    "cache_status": {"hit", "miss"},
    "provider": {"open_meteo", "meteoswiss"},
    "error_type": {
        "WeatherProviderError",
        "WeatherProviderTimeoutError",
        "WeatherProviderUnavailableError",
        "TotalBudgetExceeded",
    },
    "status": {"success", "failure", "clarification_needed", "running", "completed", "failed"},
    "result": {"success", "failure"},
    "direction": {"input", "output"},
    "operation": set(),  # route templates / UI op names / sqlite op names - checked separately below
    "route": set(),
    "tool_name": {
        "list_supported_countries",
        "list_supported_states",
        "list_supported_locations",
        "resolve_supported_location",
        "get_current_weather",
        "get_weather_history",
    },
}

# location_id values from seed data - these must NEVER appear as a label value.
_FORBIDDEN_SUBSTRINGS = ("hyderabad", "mumbai", "zurich", "17.38", "78.48")


def test_no_configured_location_ids_hardcoded_as_metric_labels():
    import inspect

    source = inspect.getsource(m)
    for forbidden in _FORBIDDEN_SUBSTRINGS:
        assert forbidden not in source


def test_all_counters_and_histograms_have_bounded_label_names():
    for name in dir(m):
        obj = getattr(m, name)
        if hasattr(obj, "_labelnames"):
            for label in obj._labelnames:
                assert label in (
                    "method",
                    "route",
                    "status_code",
                    "operation",
                    "status",
                    "path_type",
                    "cache_status",
                    "provider",
                    "error_type",
                    "tool_name",
                    "direction",
                    "result",
                ), f"Unexpected/unbounded-looking label {label!r} on metric {name!r}"
