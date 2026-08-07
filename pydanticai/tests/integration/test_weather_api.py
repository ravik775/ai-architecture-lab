from __future__ import annotations

import httpx
import respx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def _mock_response(temperature: float = 30.0) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "current": {
                "time": 1_700_000_000,
                "temperature_2m": temperature,
                "relative_humidity_2m": 50.0,
                "apparent_temperature": 31.0,
                "precipitation": 0.0,
                "weather_code": 0,
                "wind_speed_10m": 5.0,
                "wind_direction_10m": 180.0,
            }
        },
    )


def test_list_countries(app_client):
    resp = app_client.get("/v1/locations/countries")
    assert resp.status_code == 200
    codes = {c["country_code"] for c in resp.json()}
    assert codes == {"IN", "US", "CH", "LI"}


def test_list_states_filtered_by_country(app_client):
    resp = app_client.get("/v1/locations/states", params={"country_code": "IN"})
    assert resp.status_code == 200
    codes = {s["state_code"] for s in resp.json()}
    assert codes == {"TG", "MH", "DL", "KA", "TN"}


def test_list_locations_filtered_by_state(app_client):
    resp = app_client.get("/v1/locations", params={"country_code": "IN", "state_code": "TG"})
    assert resp.status_code == 200
    ids = [loc["location_id"] for loc in resp.json()]
    assert ids == ["hyderabad"]


def test_get_location_not_found(app_client):
    resp = app_client.get("/v1/locations/nowhere")
    assert resp.status_code == 404


@respx.mock
def test_current_weather_by_location_cache_hit_then_miss(app_client):
    route = respx.get(FORECAST_URL).mock(return_value=_mock_response())

    first = app_client.get("/v1/weather/current", params={"location_id": "hyderabad"})
    assert first.status_code == 200
    body = first.json()
    assert body["cache_status"] == "miss"
    assert body["location"]["location_id"] == "hyderabad"
    assert body["weather"]["temperature_c"] == 30.0
    assert body["weather"]["provider"] == "open-meteo-forecast"

    second = app_client.get("/v1/weather/current", params={"location_id": "hyderabad"})
    assert second.status_code == 200
    assert second.json()["cache_status"] == "hit"

    assert route.call_count == 1


def test_current_weather_requires_location_or_coordinates(app_client):
    resp = app_client.get("/v1/weather/current")
    assert resp.status_code == 400


def test_current_weather_unknown_location(app_client):
    resp = app_client.get("/v1/weather/current", params={"location_id": "atlantis"})
    assert resp.status_code == 404


@respx.mock
def test_current_weather_by_coordinates(app_client):
    respx.get(FORECAST_URL).mock(return_value=_mock_response(temperature=12.5))

    resp = app_client.get(
        "/v1/weather/current",
        params={"latitude": 10.0, "longitude": 20.0, "timezone": "UTC"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["location"] is None
    assert body["weather"]["temperature_c"] == 12.5


def test_current_weather_invalid_timezone(app_client):
    resp = app_client.get(
        "/v1/weather/current",
        params={"latitude": 10.0, "longitude": 20.0, "timezone": "Not/AZone"},
    )
    assert resp.status_code == 400


@respx.mock
def test_state_representative_weather_found(app_client):
    respx.get(FORECAST_URL).mock(return_value=_mock_response())

    resp = app_client.get("/v1/weather/current/state", params={"country_code": "IN", "state_code": "TG"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["representative_location"]["location_id"] == "hyderabad"
    assert "disclaimer" in body and body["disclaimer"]
    assert "not an average" in body["disclaimer"]


def test_state_representative_weather_missing_returns_candidates(app_client):
    resp = app_client.get("/v1/weather/current/state", params={"country_code": "CH", "state_code": "ZH"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["representative_location"] is None
    assert body["message"] is not None
    ids = [loc["location_id"] for loc in body["supported_locations"]]
    assert "zurich" in ids


def test_health_live_and_ready(app_client):
    assert app_client.get("/health/live").status_code == 200
    assert app_client.get("/health/ready").status_code == 200


def test_ui_mounted_and_serves_page(app_client_with_ui):
    resp = app_client_with_ui.get("/ui/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Weather Intelligence Agent" in resp.text


@respx.mock
def test_direct_weather_path_never_invokes_the_agent(app_client):
    """The low-latency weather path must never touch the LLM/agent - break
    the agent and confirm /v1/weather/current is completely unaffected."""

    async def _boom(*args, **kwargs):
        raise AssertionError("agent_service.query must never be called from the weather path")

    app_client.app.state.agent_service.query = _boom
    respx.get(FORECAST_URL).mock(return_value=_mock_response())

    resp = app_client.get("/v1/weather/current", params={"location_id": "hyderabad"})
    assert resp.status_code == 200
    assert resp.json()["cache_status"] == "miss"
