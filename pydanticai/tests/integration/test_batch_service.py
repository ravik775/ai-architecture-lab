from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.application.batch_service import BatchService
from app.config.settings import SchedulerSettings
from app.domain.errors import BatchAlreadyRunningError
from app.domain.models import CollectionType, ProviderName, WeatherObservation
from app.infrastructure.database.models import Base
from app.infrastructure.database.repositories import JobRepository, LocationRepository, ObservationRepository
from app.infrastructure.database.seed import seed
from app.infrastructure.database.session import Database


class _SelectiveFailureProvider:
    """Fails for a configured set of location_ids, succeeds for the rest."""

    def __init__(self, fail_for: set[str] | None = None) -> None:
        self.fail_for = fail_for or set()
        self.call_count = 0

    async def get_daily_weather(self, *, location_id: str, target_date: date, **kwargs) -> WeatherObservation:
        self.call_count += 1
        if location_id in self.fail_for:
            raise RuntimeError(f"simulated upstream failure for {location_id}")
        return WeatherObservation(
            location_id=location_id,
            latitude=kwargs["latitude"],
            longitude=kwargs["longitude"],
            observation_time_utc=datetime.now(UTC),
            local_date=target_date,
            temperature_c=15.0,
            apparent_temperature_c=14.0,
            humidity_percent=60.0,
            precipitation_mm=0.0,
            weather_code=2,
            wind_speed_kmh=8.0,
            wind_direction_deg=270.0,
            provider=ProviderName.OPEN_METEO_FORECAST,
            model="auto",
            unit_system="metric",
            collection_type=CollectionType.DAILY_BATCH,
        )

    async def get_current_weather(self, **kwargs):  # pragma: no cover - unused in batch tests
        raise NotImplementedError


@pytest.fixture()
async def batch_env(tmp_path, monkeypatch):
    db_path = (tmp_path / "batch.db").as_posix()
    monkeypatch.setenv("DATABASE__URL", f"sqlite+aiosqlite:///{db_path}")

    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    db = Database(settings.database)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed()

    yield db, settings
    await db.dispose()
    get_settings.cache_clear()


def _make_batch_service(db, settings, provider, *, batch_concurrency: int = 5) -> BatchService:
    return BatchService(
        provider=provider,
        db=db,
        location_repository=LocationRepository(),
        observation_repository=ObservationRepository(),
        job_repository=JobRepository(),
        scheduler_settings=SchedulerSettings(batch_concurrency=batch_concurrency),
    )


async def test_partial_failure_isolated_and_recorded(batch_env):
    db, settings = batch_env
    provider = _SelectiveFailureProvider(fail_for={"mumbai", "chicago"})
    service = _make_batch_service(db, settings, provider)

    run = await service.run_daily_collection(trigger_source="manual")

    assert run.status == "partial_success"
    assert run.total_location_count == 15
    assert run.failure_count == 2
    assert run.success_count == 13
    assert run.error_summary is not None
    assert "mumbai" in run.error_summary


async def test_idempotent_upsert_no_duplicate_rows_on_rerun(batch_env):
    db, settings = batch_env
    provider = _SelectiveFailureProvider()
    service = _make_batch_service(db, settings, provider)

    await service.run_daily_collection(trigger_source="manual")
    await service.run_daily_collection(trigger_source="manual")

    from sqlalchemy import func, select

    from app.infrastructure.database.models import WeatherObservationRow

    async with db.session() as session:
        total = (
            await session.execute(select(func.count()).select_from(WeatherObservationRow))
        ).scalar_one()
        hyderabad_rows = (
            await session.execute(
                select(func.count())
                .select_from(WeatherObservationRow)
                .where(WeatherObservationRow.location_id == "hyderabad")
            )
        ).scalar_one()

    assert total == 15  # not 30 - the second run upserted, not inserted
    assert hyderabad_rows == 1


async def test_overlap_prevention_rejects_concurrent_run(batch_env):
    db, settings = batch_env
    provider = _SelectiveFailureProvider()
    service = _make_batch_service(db, settings, provider)

    import asyncio

    results = await asyncio.gather(
        service.run_daily_collection(trigger_source="manual"),
        service.run_daily_collection(trigger_source="manual"),
        return_exceptions=True,
    )

    successes = [r for r in results if not isinstance(r, Exception)]
    rejections = [r for r in results if isinstance(r, BatchAlreadyRunningError)]
    assert len(successes) == 1
    assert len(rejections) == 1


async def test_location_filter_scopes_collection_to_timezone_group(batch_env):
    db, settings = batch_env
    provider = _SelectiveFailureProvider()
    service = _make_batch_service(db, settings, provider)

    run = await service.run_daily_collection(trigger_source="scheduled", location_ids=["hyderabad", "mumbai"])

    assert run.total_location_count == 2
    assert provider.call_count == 2
