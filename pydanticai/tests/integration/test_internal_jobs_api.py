from __future__ import annotations

import httpx
import respx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def _mock_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "current": {
                "time": 1_700_000_000,
                "temperature_2m": 18.0,
                "relative_humidity_2m": 60.0,
                "apparent_temperature": 17.0,
                "precipitation": 0.0,
                "weather_code": 1,
                "wind_speed_10m": 4.0,
                "wind_direction_10m": 90.0,
            }
        },
    )


def test_trigger_without_token_rejected(app_client):
    resp = app_client.post("/internal/jobs/daily-weather")
    assert resp.status_code == 401


def test_trigger_with_wrong_token_rejected(app_client):
    resp = app_client.post("/internal/jobs/daily-weather", headers={"X-Internal-Token": "nope"})
    assert resp.status_code == 401


@respx.mock
def test_trigger_and_fetch_job(app_client):
    respx.get(FORECAST_URL).mock(return_value=_mock_response())

    resp = app_client.post(
        "/internal/jobs/daily-weather", headers={"X-Internal-Token": "test-internal-token"}
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] in ("completed", "partial_success")
    assert body["total_location_count"] == 15

    job_id = body["job_id"]
    fetched = app_client.get(
        f"/internal/jobs/daily-weather/{job_id}", headers={"X-Internal-Token": "test-internal-token"}
    )
    assert fetched.status_code == 200
    assert fetched.json()["job_id"] == job_id


def test_get_unknown_job_404(app_client):
    resp = app_client.get(
        "/internal/jobs/daily-weather/does-not-exist", headers={"X-Internal-Token": "test-internal-token"}
    )
    assert resp.status_code == 404
