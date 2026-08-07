"""Daily collection batch job - an application-level asyncio job, NOT an
LLM batch API. Retrieves weather from Open-Meteo for preconfigured
locations and persists it, isolating per-location failures so one bad
location never aborts the whole run.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.config.settings import SchedulerSettings
from app.domain.errors import BatchAlreadyRunningError
from app.domain.protocols import WeatherProvider
from app.infrastructure.database.models import ConfiguredLocationRow, DailyCollectionRunRow
from app.infrastructure.database.repositories import JobRepository, LocationRepository, ObservationRepository
from app.infrastructure.database.session import Database
from app.infrastructure.database.utils import as_utc
from app.observability.metrics import batch_locations_total, batch_run_duration_seconds, batch_runs_total
from app.observability.tracing import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

_MAX_ERROR_SUMMARY_ENTRIES = 20


class BatchService:
    def __init__(
        self,
        provider: WeatherProvider,
        db: Database,
        location_repository: LocationRepository,
        observation_repository: ObservationRepository,
        job_repository: JobRepository,
        scheduler_settings: SchedulerSettings,
    ) -> None:
        self._provider = provider
        self._db = db
        self._location_repository = location_repository
        self._observation_repository = observation_repository
        self._job_repository = job_repository
        self._scheduler_settings = scheduler_settings
        self._run_lock = asyncio.Lock()

    async def _reject_if_overlapping(self) -> None:
        async with self._db.session() as session:
            active = await self._job_repository.get_active_run(session)
            if active is None:
                return
            age_seconds = (datetime.now(UTC) - as_utc(active.scheduled_time)).total_seconds()
            if age_seconds < self._scheduler_settings.stale_run_timeout_seconds:
                raise BatchAlreadyRunningError(active.job_id)
            logger.warning(
                "treating run %s as abandoned (running for %.0fs, exceeds stale_run_timeout_seconds=%s)",
                active.job_id,
                age_seconds,
                self._scheduler_settings.stale_run_timeout_seconds,
            )
            await self._job_repository.mark_finished(
                session,
                job_id=active.job_id,
                finish_time=datetime.now(UTC),
                status="abandoned",
                success_count=active.success_count,
                failure_count=active.failure_count,
                error_summary=json.dumps([{"error": "marked abandoned: exceeded stale_run_timeout_seconds"}]),
            )
            await session.commit()

    async def run_daily_collection(
        self, *, trigger_source: str, location_ids: list[str] | None = None
    ) -> DailyCollectionRunRow:
        if self._run_lock.locked():
            async with self._db.session() as session:
                active = await self._job_repository.get_active_run(session)
            raise BatchAlreadyRunningError(active.job_id if active else "unknown")

        async with self._run_lock:
            await self._reject_if_overlapping()

            locations = await self._select_locations(location_ids)
            job_id = str(uuid.uuid4())
            now = datetime.now(UTC)

            async with self._db.session() as session:
                await self._job_repository.create_run(
                    session, job_id=job_id, scheduled_time=now, total_location_count=len(locations)
                )
                await session.commit()
            async with self._db.session() as session:
                await self._job_repository.mark_running(session, job_id=job_id, start_time=now)
                await session.commit()

            started = time.perf_counter()
            with tracer.start_as_current_span("batch_service.run_daily_collection") as span:
                span.set_attribute("batch.job_id", job_id)
                span.set_attribute("batch.trigger_source", trigger_source)
                span.set_attribute("batch.location_count", len(locations))

                success_count, failure_count, errors = await self._collect_all(job_id, locations)

            duration = time.perf_counter() - started
            status = "completed" if failure_count == 0 else ("partial_success" if success_count > 0 else "failed")

            async with self._db.session() as session:
                await self._job_repository.mark_finished(
                    session,
                    job_id=job_id,
                    finish_time=datetime.now(UTC),
                    status=status,
                    success_count=success_count,
                    failure_count=failure_count,
                    error_summary=json.dumps(errors[:_MAX_ERROR_SUMMARY_ENTRIES]) if errors else None,
                )
                await session.commit()
                run = await self._job_repository.get_run(session, job_id)

            batch_runs_total.labels(status=status).inc()
            batch_run_duration_seconds.observe(duration)
            logger.info(
                "daily collection run %s finished: status=%s success=%d failure=%d duration=%.2fs",
                job_id,
                status,
                success_count,
                failure_count,
                duration,
            )
            assert run is not None
            return run

    async def _select_locations(self, location_ids: list[str] | None) -> list[ConfiguredLocationRow]:
        async with self._db.session() as session:
            all_locations = await self._location_repository.list_daily_collection_locations(session)
        if location_ids is None:
            return all_locations
        wanted = set(location_ids)
        return [loc for loc in all_locations if loc.location_id in wanted]

    async def _collect_all(
        self, job_id: str, locations: list[ConfiguredLocationRow]
    ) -> tuple[int, int, list[dict]]:
        semaphore = asyncio.Semaphore(self._scheduler_settings.batch_concurrency)
        success_count = 0
        failure_count = 0
        errors: list[dict] = []

        async def _collect_one(location: ConfiguredLocationRow) -> None:
            nonlocal success_count, failure_count
            async with semaphore:
                try:
                    target_date = datetime.now(ZoneInfo(location.timezone)).date()
                    observation = await self._provider.get_daily_weather(
                        latitude=location.latitude,
                        longitude=location.longitude,
                        timezone=location.timezone,
                        target_date=target_date,
                        provider_preference=location.provider_preference,
                        location_id=location.location_id,
                    )
                    async with self._db.session() as session:
                        await self._observation_repository.upsert_observation(
                            session,
                            location_id=location.location_id,
                            observation_date=observation.local_date,
                            observation_timestamp_utc=observation.observation_time_utc,
                            local_date=observation.local_date,
                            temperature_c=observation.temperature_c,
                            apparent_temperature_c=observation.apparent_temperature_c,
                            humidity_percent=observation.humidity_percent,
                            precipitation_mm=observation.precipitation_mm,
                            weather_code=observation.weather_code,
                            wind_speed_kmh=observation.wind_speed_kmh,
                            wind_direction_deg=observation.wind_direction_deg,
                            provider=observation.provider.value,
                            model=observation.model,
                            unit_system=observation.unit_system,
                            collection_type=observation.collection_type.value,
                        )
                        await session.commit()
                    success_count += 1
                    batch_locations_total.labels(result="success").inc()
                except Exception as exc:  # noqa: BLE001 - isolate per-location failures by design
                    failure_count += 1
                    batch_locations_total.labels(result="failure").inc()
                    logger.exception("daily collection failed for location %s (job %s)", location.location_id, job_id)
                    errors.append({"location_id": location.location_id, "error": str(exc)[:200]})

        await asyncio.gather(*(_collect_one(loc) for loc in locations))
        return success_count, failure_count, errors
