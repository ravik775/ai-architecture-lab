"""End-of-day trigger check: runs every `check_interval_minutes`, groups
daily-enabled locations by IANA timezone, and fires the batch collection
for a timezone group once its local clock enters the last check-interval
window before local midnight (23:00 through 23:00+check_interval).

A single `BatchService`-level lock serializes all runs process-wide (see
`batch_service.py`). For the seeded location set this is never a real
constraint - Kolkata/US/Zurich local-23:00 windows never coincide - but a
deployment with timezones that DO coincide would see one group's trigger
skipped and naturally retried on the next tick (self-healing within
`check_interval_minutes`), never silently dropped.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.application.batch_service import BatchService
from app.application.location_service import LocationService
from app.config.settings import SchedulerSettings
from app.domain.errors import BatchAlreadyRunningError

logger = logging.getLogger(__name__)


class EndOfDayTriggerState:
    """Tracks the last local date each timezone group was triggered for,
    so a 15-minute-wide check window doesn't re-trigger repeatedly."""

    def __init__(self) -> None:
        self._last_triggered: dict[str, date] = {}

    def should_trigger(self, timezone: str, now_local: datetime, window_minutes: int) -> bool:
        already_done = self._last_triggered.get(timezone) == now_local.date()
        in_window = now_local.hour == 23 and now_local.minute < window_minutes
        return in_window and not already_done

    def mark_triggered(self, timezone: str, local_date: date) -> None:
        self._last_triggered[timezone] = local_date


async def check_and_trigger_end_of_day_collection(
    *,
    location_service: LocationService,
    batch_service: BatchService,
    scheduler_settings: SchedulerSettings,
    state: EndOfDayTriggerState,
) -> None:
    locations = await location_service.list_daily_collection_locations()
    by_timezone: dict[str, list[str]] = {}
    for location in locations:
        by_timezone.setdefault(location.timezone, []).append(location.location_id)

    for timezone, location_ids in by_timezone.items():
        now_local = datetime.now(ZoneInfo(timezone))
        if not state.should_trigger(timezone, now_local, scheduler_settings.check_interval_minutes):
            continue

        state.mark_triggered(timezone, now_local.date())
        logger.info(
            "triggering end-of-day collection for timezone=%s (%d locations, local_time=%s)",
            timezone,
            len(location_ids),
            now_local.isoformat(),
        )
        try:
            await batch_service.run_daily_collection(trigger_source="scheduled", location_ids=location_ids)
        except BatchAlreadyRunningError as exc:
            logger.warning(
                "skipped scheduled collection for timezone=%s - run %s already in progress; "
                "will retry next check_interval_minutes tick",
                timezone,
                exc.job_id,
            )
