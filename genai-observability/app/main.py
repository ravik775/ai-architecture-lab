from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.api.routes import router
from app.config import get_settings
from app.health.monitor import HealthMonitor
from app.llm.chain import ChatGraphRunner
from app.llm.memory import store
from app.observability.metrics import configure_metrics
from app.observability.redaction import PIIRedactionLogFilter
from app.observability.setup import configure_observability
from app.security.auth import auth_enabled

settings = get_settings()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)

# Layer 4 of the PII redaction plan (docs/SECURITY-PLAN.md Section 2.1):
# registered on the root logger so it runs for every logger in this app
# (all of them propagate to root by default) - a safety net for a future
# debug log line that shouldn't ship raw PII, not the primary control
# (that's Layer 1, app/observability/redaction.py::RedactingSpanExporter).
if settings.pii_redaction_enabled:
    logging.getLogger().addFilter(PIIRedactionLogFilter())

logger = logging.getLogger("app")


def _build_component_checks(settings) -> dict:
    def config_ok() -> bool:
        return bool(settings.openrouter_api_key)

    def memory_store_ok() -> bool:
        # Cheap structural check - store must be reachable and countable.
        store.session_count()
        return True

    return {
        "config": config_ok,
        "memory_store": memory_store_ok,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    tracer_provider = configure_observability(settings)
    meter_provider = configure_metrics(settings)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider, meter_provider=meter_provider)

    app.state.chat_runner = ChatGraphRunner(settings)
    app.state.health_monitor = HealthMonitor(
        interval_seconds=settings.health_check_interval_seconds,
        summary_window_seconds=settings.health_summary_window_seconds,
        component_checks=_build_component_checks(settings),
    )
    app.state.health_monitor.start()

    logger.info(
        "Startup complete | service=%s env=%s provider=%s model=%s",
        settings.service_name,
        settings.app_env,
        settings.observability_provider.value,
        settings.openrouter_model,
    )
    if not settings.openrouter_api_key:
        logger.warning("OPENROUTER_API_KEY is not set - /chat calls will fail until it is configured.")

    if auth_enabled():
        logger.info("API-key auth is ENABLED on /chat* (API_KEYS configured).")
    else:
        logger.warning(
            "API_KEYS is not set - /chat* is running WITHOUT authentication. "
            "Set API_KEYS (see .env.example) before exposing this beyond localhost."
        )

    yield

    await app.state.health_monitor.stop()
    logger.info("Shutdown complete")


app = FastAPI(
    title="GenAI Observability Reference Service",
    version=settings.service_version,
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/")
async def root() -> dict:
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "observability_provider": settings.observability_provider.value,
        "docs": "/docs",
    }
