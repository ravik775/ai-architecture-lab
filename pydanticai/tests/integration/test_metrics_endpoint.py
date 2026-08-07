from __future__ import annotations

import httpx
import pytest
import respx

from app.observability.metrics import render_latest, start_metrics_server, stop_metrics_server

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def test_metrics_not_reachable_on_the_main_app_port(app_client):
    """`/metrics` deliberately does NOT exist on the main FastAPI app - it's
    served on its own port precisely so it can be firewalled independently
    (see settings.py's `metrics_port` docstring). This is a regression
    guard for that separation, not just a happy-path check."""
    resp = app_client.get("/metrics")
    assert resp.status_code == 404


def test_metrics_server_serves_prometheus_text_on_its_own_port():
    server = start_metrics_server(0, addr="127.0.0.1")  # port 0 = OS-assigned free port
    try:
        port = server.server_port
        resp = httpx.get(f"http://127.0.0.1:{port}/metrics", timeout=5.0)
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        assert "http_requests_total" in resp.text
    finally:
        stop_metrics_server(server)


@respx.mock
def test_metrics_reflect_weather_requests(app_client):
    respx.get(FORECAST_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "current": {
                    "time": 1_700_000_000,
                    "temperature_2m": 22.0,
                    "relative_humidity_2m": 40.0,
                    "apparent_temperature": 21.0,
                    "precipitation": 0.0,
                    "weather_code": 0,
                    "wind_speed_10m": 3.0,
                    "wind_direction_10m": 90.0,
                }
            },
        )
    )
    app_client.get("/v1/weather/current", params={"location_id": "hyderabad"})

    # Inspected directly from the registry rather than over HTTP - the
    # registry is process-wide and identical either way, and this avoids
    # needing a live metrics server just to check a counter incremented.
    body, _content_type = render_latest()
    text = body.decode()
    assert 'weather_requests_total{cache_status="miss",path_type="location"}' in text
    assert "cache_misses_total" in text


def test_response_has_request_id_header(app_client):
    resp = app_client.get("/health/live")
    assert "x-request-id" in {k.lower() for k in resp.headers.keys()}
