from typing import Any
import httpx

from app.tools.base import Tool


class WeatherTool(Tool):
    name = 'weather'
    description = 'Gets current weather for a city using Open-Meteo public APIs.'

    def run(self, city: str, **_: Any) -> dict[str, Any]:
        with httpx.Client(timeout=15) as client:
            geo = client.get(
                'https://geocoding-api.open-meteo.com/v1/search',
                params={'name': city, 'count': 1, 'language': 'en', 'format': 'json'},
            )
            geo.raise_for_status()
            results = geo.json().get('results') or []
            if not results:
                return {'city': city, 'error': 'City not found'}

            place = results[0]
            latitude = place['latitude']
            longitude = place['longitude']

            forecast = client.get(
                'https://api.open-meteo.com/v1/forecast',
                params={
                    'latitude': latitude,
                    'longitude': longitude,
                    'current': 'temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code',
                    'timezone': 'auto',
                },
            )
            forecast.raise_for_status()
            current = forecast.json().get('current', {})
            return {
                'city': place.get('name', city),
                'country': place.get('country'),
                'latitude': latitude,
                'longitude': longitude,
                'temperature_c': current.get('temperature_2m'),
                'humidity_percent': current.get('relative_humidity_2m'),
                'wind_speed_kmh': current.get('wind_speed_10m'),
                'weather_code': current.get('weather_code'),
                'source': 'Open-Meteo',
            }
