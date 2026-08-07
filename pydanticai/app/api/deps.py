"""FastAPI dependency accessors - all pull already-constructed, app-scoped
singletons off `app.state` (built once in `main.py`'s lifespan)."""
from __future__ import annotations

from fastapi import Header, HTTPException, Request

from app.application.auth_service import AuthService
from app.application.history_service import HistoryService
from app.application.location_service import LocationService
from app.application.weather_service import WeatherService
from app.config.settings import Settings
from app.security.jwt_tokens import decode_access_token


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_weather_service(request: Request) -> WeatherService:
    return request.app.state.weather_service


def get_location_service(request: Request) -> LocationService:
    return request.app.state.location_service


def get_history_service(request: Request) -> HistoryService:
    return request.app.state.history_service


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


async def get_current_claims(request: Request, authorization: str | None = Header(None)) -> dict:
    """Standard `Authorization: Bearer <jwt>` check - unrelated to the
    `force_trace` RBAC gate in `app/observability/sampling.py`, which reads
    the token from OTel baggage instead because it has to run before this
    middleware/dependency layer even executes (see that module's docstring)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1]
    claims = decode_access_token(token, request.app.state.settings.security)
    if claims is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return claims
