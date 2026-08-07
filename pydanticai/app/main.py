"""FastAPI application factory and process entrypoint."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agent.agent import AgentService, build_agent
from app.agent.deps import AgentDeps
from app.api.health import router as health_router
from app.api.internal.jobs import router as internal_jobs_router
from app.api.internal.users import router as internal_users_router
from app.api.v1.agent import router as agent_router
from app.api.v1.auth import router as auth_router
from app.api.v1.history import router as history_router
from app.api.v1.locations import router as locations_router
from app.api.v1.weather import router as weather_router
from app.application.auth_service import AuthService
from app.application.batch_service import BatchService
from app.application.history_service import HistoryService
from app.application.location_service import LocationService
from app.application.weather_service import WeatherService
from app.config import Settings, get_settings
from app.infrastructure.database.repositories import (
    JobRepository,
    LocationRepository,
    ObservationRepository,
    UserRepository,
)
from app.infrastructure.database.session import Database
from app.infrastructure.weather.cache import InMemoryWeatherCache
from app.infrastructure.weather.http_client import close_http_client, create_http_client
from app.infrastructure.weather.open_meteo_provider import OpenMeteoWeatherProvider
from app.observability.logging import configure_logging
from app.observability.metrics import start_metrics_server, stop_metrics_server
from app.observability.middleware import RequestContextMiddleware
from app.observability.tracing import configure_tracing, instrument_fastapi, instrument_sqlalchemy, shutdown_tracing
from app.scheduler.apscheduler_setup import SchedulerManager
from app.security.rate_limit import IPRateLimitMiddleware
from app.ui.pages import register_ui


def _wire_services(app: FastAPI, settings: Settings) -> None:
    app.state.settings = settings
    app.state.db = Database(settings.database)
    app.state.http_client = create_http_client(settings.http_client)

    location_repository = LocationRepository()
    observation_repository = ObservationRepository()
    job_repository = JobRepository()
    user_repository = UserRepository()
    app.state.location_repository = location_repository
    app.state.observation_repository = observation_repository
    app.state.job_repository = job_repository
    app.state.user_repository = user_repository

    weather_provider = OpenMeteoWeatherProvider(
        app.state.http_client, settings.weather_provider, settings.http_client
    )
    weather_cache = InMemoryWeatherCache(settings.cache)
    app.state.weather_provider = weather_provider
    app.state.weather_cache = weather_cache

    app.state.weather_service = WeatherService(
        provider=weather_provider,
        cache=weather_cache,
        db=app.state.db,
        location_repository=location_repository,
        cache_settings=settings.cache,
        http_settings=settings.http_client,
    )
    app.state.location_service = LocationService(app.state.db, location_repository)
    app.state.history_service = HistoryService(
        app.state.db,
        observation_repository,
        max_range_days=settings.security.max_history_range_days,
        max_page_size=settings.security.max_page_size,
    )
    app.state.batch_service = BatchService(
        provider=weather_provider,
        db=app.state.db,
        location_repository=location_repository,
        observation_repository=observation_repository,
        job_repository=job_repository,
        scheduler_settings=settings.scheduler,
    )
    app.state.scheduler_manager = SchedulerManager(
        settings.scheduler, app.state.location_service, app.state.batch_service
    )
    app.state.auth_service = AuthService(app.state.db, user_repository, settings.security)

    def _agent_deps_factory() -> AgentDeps:
        return AgentDeps(
            location_service=app.state.location_service,
            weather_service=app.state.weather_service,
            history_service=app.state.history_service,
        )

    agent = build_agent(settings.agent)
    app.state.agent_service = AgentService(agent, _agent_deps_factory, settings.agent)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(level=settings.log_level, service_name=settings.observability.service_name)
    configure_tracing(settings.observability, settings.security)
    _wire_services(app, settings)
    instrument_sqlalchemy(app.state.db.engine.sync_engine)
    await app.state.auth_service.bootstrap_default_user()
    app.state.scheduler_manager.start()

    app.state.metrics_server = None
    if settings.observability.metrics_server_enabled:
        app.state.metrics_server = start_metrics_server(
            settings.observability.metrics_port, addr=settings.observability.metrics_bind_host
        )

    yield

    if app.state.metrics_server is not None:
        stop_metrics_server(app.state.metrics_server)
    app.state.scheduler_manager.shutdown()
    await close_http_client(app.state.http_client)
    await app.state.db.dispose()
    shutdown_tracing()


def create_app(*, mount_ui: bool = True) -> FastAPI:
    """`mount_ui=False` exists for tests: NiceGUI's `ui.run_with()` mounts
    onto a process-wide singleton (`nicegui.core.app`) whose middleware
    stack can only be built once per process - calling it from every
    test's fresh `create_app()` fails on the second call with "Cannot add
    middleware after an application has started". Production always mounts
    the UI (`app/main.py`'s module-level `app = create_app()` runs exactly
    once); most tests don't touch `/ui/` and can skip it.
    """
    app = FastAPI(
        title="Weather Intelligence Agent",
        version="0.1.0",
        docs_url="/docs",
        lifespan=lifespan,
    )

    # Registration order matters: Starlette makes the LAST-added middleware
    # outermost, so RequestContextMiddleware (added last) still assigns
    # request_id/correlation_id and logs "request completed" even for a
    # request the rate limiter rejects with 429.
    app.add_middleware(IPRateLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)
    instrument_fastapi(app)

    app.include_router(health_router)
    app.include_router(locations_router)
    app.include_router(weather_router)
    app.include_router(history_router)
    app.include_router(internal_jobs_router)
    app.include_router(internal_users_router)
    app.include_router(agent_router)
    app.include_router(auth_router)

    if mount_ui:
        register_ui(app, get_settings())

    return app


app = create_app()
