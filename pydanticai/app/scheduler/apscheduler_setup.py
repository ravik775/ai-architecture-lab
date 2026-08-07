"""In-process APScheduler wiring.

Single-replica limitation: this scheduler lives inside the `weather-app`
process. Running more than one replica would mean every replica fires the
same end-of-day check independently, duplicating (though not corrupting,
thanks to the idempotent UPSERT + run-overlap lock) collection attempts.
A horizontally-scaled deployment should replace this with an external
scheduler (e.g. a cron-triggered job or a workflow engine) calling
`POST /internal/jobs/daily-weather` on exactly one instance, with the
in-app scheduler disabled via `SCHEDULER__ENABLED=false`.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.application.batch_service import BatchService
from app.application.location_service import LocationService
from app.config.settings import SchedulerSettings
from app.observability.metrics import scheduler_misfires_total
from app.scheduler.jobs import EndOfDayTriggerState, check_and_trigger_end_of_day_collection

logger = logging.getLogger(__name__)

_JOB_ID = "end_of_day_collection_check"


class SchedulerManager:
    def __init__(
        self,
        settings: SchedulerSettings,
        location_service: LocationService,
        batch_service: BatchService,
    ) -> None:
        self._settings = settings
        self._location_service = location_service
        self._batch_service = batch_service
        self._state = EndOfDayTriggerState()
        self._scheduler = AsyncIOScheduler()

    def _on_job_missed(self, event) -> None:  # noqa: ANN001
        if event.job_id == _JOB_ID:
            scheduler_misfires_total.inc()
            logger.warning("scheduler misfire for job %s", event.job_id)

    def start(self) -> None:
        if not self._settings.enabled:
            logger.info("scheduler disabled via SCHEDULER__ENABLED=false")
            return

        from apscheduler.events import EVENT_JOB_MISSED

        self._scheduler.add_listener(self._on_job_missed, EVENT_JOB_MISSED)
        self._scheduler.add_job(
            self._tick,
            trigger=IntervalTrigger(minutes=self._settings.check_interval_minutes),
            id=_JOB_ID,
            misfire_grace_time=self._settings.misfire_grace_time_seconds,
            coalesce=True,
            max_instances=1,
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info("scheduler started: checking every %d minutes", self._settings.check_interval_minutes)

    async def _tick(self) -> None:
        await check_and_trigger_end_of_day_collection(
            location_service=self._location_service,
            batch_service=self._batch_service,
            scheduler_settings=self._settings,
            state=self._state,
        )

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=True)
            logger.info("scheduler shut down gracefully")
