"""Repositories - thin, session-scoped data access. Callers (application
services) own the session/transaction boundary; repositories never commit.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    ConfiguredLocationRow,
    CountryRow,
    DailyCollectionRunRow,
    StateRow,
    UserRow,
    WeatherObservationRow,
)


class LocationRepository:
    async def list_countries(self, session: AsyncSession, *, active_only: bool = True) -> list[CountryRow]:
        stmt = select(CountryRow).order_by(CountryRow.country_name)
        if active_only:
            stmt = stmt.where(CountryRow.active.is_(True))
        return list((await session.execute(stmt)).scalars().all())

    async def get_country(self, session: AsyncSession, country_code: str) -> CountryRow | None:
        return await session.get(CountryRow, country_code)

    async def list_states(
        self, session: AsyncSession, *, country_code: str, active_only: bool = True
    ) -> list[StateRow]:
        stmt = select(StateRow).where(StateRow.country_code == country_code).order_by(StateRow.state_name)
        if active_only:
            stmt = stmt.where(StateRow.active.is_(True))
        return list((await session.execute(stmt)).scalars().all())

    async def get_state(
        self, session: AsyncSession, *, country_code: str, state_code: str
    ) -> StateRow | None:
        stmt = select(StateRow).where(
            StateRow.country_code == country_code, StateRow.state_code == state_code
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def list_locations(
        self,
        session: AsyncSession,
        *,
        country_code: str | None = None,
        state_code: str | None = None,
        active_only: bool = True,
    ) -> list[ConfiguredLocationRow]:
        stmt = select(ConfiguredLocationRow).order_by(ConfiguredLocationRow.location_name)
        if country_code:
            stmt = stmt.where(ConfiguredLocationRow.country_code == country_code)
        if state_code:
            stmt = stmt.where(ConfiguredLocationRow.state_code == state_code)
        if active_only:
            stmt = stmt.where(ConfiguredLocationRow.active.is_(True))
        return list((await session.execute(stmt)).scalars().all())

    async def get_location(
        self, session: AsyncSession, location_id: str
    ) -> ConfiguredLocationRow | None:
        return await session.get(ConfiguredLocationRow, location_id)

    async def search_locations_by_name(
        self, session: AsyncSession, query: str, *, limit: int = 10
    ) -> list[ConfiguredLocationRow]:
        stmt = (
            select(ConfiguredLocationRow)
            .where(
                ConfiguredLocationRow.active.is_(True),
                ConfiguredLocationRow.location_name.ilike(f"%{query}%"),
            )
            .order_by(ConfiguredLocationRow.location_name)
            .limit(limit)
        )
        return list((await session.execute(stmt)).scalars().all())

    async def get_representative_location(
        self, session: AsyncSession, *, country_code: str, state_code: str
    ) -> ConfiguredLocationRow | None:
        state = await self.get_state(session, country_code=country_code, state_code=state_code)
        if state is None or state.representative_location_id is None:
            return None
        return await self.get_location(session, state.representative_location_id)

    async def list_daily_collection_locations(
        self, session: AsyncSession
    ) -> list[ConfiguredLocationRow]:
        stmt = select(ConfiguredLocationRow).where(
            ConfiguredLocationRow.active.is_(True),
            ConfiguredLocationRow.daily_collection_enabled.is_(True),
        )
        return list((await session.execute(stmt)).scalars().all())


class ObservationRepository:
    async def upsert_observation(
        self,
        session: AsyncSession,
        *,
        location_id: str,
        observation_date: date,
        observation_timestamp_utc: datetime,
        local_date: date,
        temperature_c: float,
        apparent_temperature_c: float,
        humidity_percent: float,
        precipitation_mm: float,
        weather_code: int,
        wind_speed_kmh: float,
        wind_direction_deg: float,
        provider: str,
        model: str,
        unit_system: str,
        collection_type: str,
    ) -> None:
        """Idempotent on (location_id, observation_date, provider, collection_type)."""
        values = dict(
            location_id=location_id,
            observation_date=observation_date,
            observation_timestamp_utc=observation_timestamp_utc,
            local_date=local_date,
            temperature_c=temperature_c,
            apparent_temperature_c=apparent_temperature_c,
            humidity_percent=humidity_percent,
            precipitation_mm=precipitation_mm,
            weather_code=weather_code,
            wind_speed_kmh=wind_speed_kmh,
            wind_direction_deg=wind_direction_deg,
            provider=provider,
            model=model,
            unit_system=unit_system,
            collection_type=collection_type,
        )
        stmt = sqlite_insert(WeatherObservationRow).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["location_id", "observation_date", "provider", "collection_type"],
            set_={k: v for k, v in values.items() if k not in ("location_id", "observation_date", "provider", "collection_type")},
        )
        await session.execute(stmt)

    async def list_history(
        self,
        session: AsyncSession,
        *,
        location_id: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[WeatherObservationRow], int]:
        conditions = []
        if location_id:
            conditions.append(WeatherObservationRow.location_id == location_id)
        if start_date:
            conditions.append(WeatherObservationRow.local_date >= start_date)
        if end_date:
            conditions.append(WeatherObservationRow.local_date <= end_date)

        base_stmt = select(WeatherObservationRow)
        count_stmt = select(func.count()).select_from(WeatherObservationRow)
        for cond in conditions:
            base_stmt = base_stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        base_stmt = base_stmt.order_by(
            WeatherObservationRow.local_date.desc(), WeatherObservationRow.location_id
        ).limit(limit).offset(offset)

        rows = list((await session.execute(base_stmt)).scalars().all())
        total = (await session.execute(count_stmt)).scalar_one()
        return rows, total


class JobRepository:
    async def create_run(
        self,
        session: AsyncSession,
        *,
        job_id: str,
        scheduled_time: datetime,
        total_location_count: int,
    ) -> DailyCollectionRunRow:
        row = DailyCollectionRunRow(
            job_id=job_id,
            scheduled_time=scheduled_time,
            status="pending",
            total_location_count=total_location_count,
            success_count=0,
            failure_count=0,
        )
        session.add(row)
        await session.flush()
        return row

    async def mark_running(self, session: AsyncSession, *, job_id: str, start_time: datetime) -> None:
        row = await session.get(DailyCollectionRunRow, job_id)
        if row is not None:
            row.status = "running"
            row.start_time = start_time

    async def mark_finished(
        self,
        session: AsyncSession,
        *,
        job_id: str,
        finish_time: datetime,
        status: str,
        success_count: int,
        failure_count: int,
        error_summary: str | None,
    ) -> None:
        row = await session.get(DailyCollectionRunRow, job_id)
        if row is not None:
            row.status = status
            row.finish_time = finish_time
            row.success_count = success_count
            row.failure_count = failure_count
            row.error_summary = error_summary

    async def get_run(self, session: AsyncSession, job_id: str) -> DailyCollectionRunRow | None:
        return await session.get(DailyCollectionRunRow, job_id)

    async def get_latest_run(self, session: AsyncSession) -> DailyCollectionRunRow | None:
        stmt = select(DailyCollectionRunRow).order_by(DailyCollectionRunRow.created_at.desc()).limit(1)
        return (await session.execute(stmt)).scalar_one_or_none()

    async def has_active_run(self, session: AsyncSession) -> bool:
        stmt = select(func.count()).select_from(DailyCollectionRunRow).where(
            DailyCollectionRunRow.status.in_(["pending", "running"])
        )
        return (await session.execute(stmt)).scalar_one() > 0

    async def get_active_run(self, session: AsyncSession) -> DailyCollectionRunRow | None:
        stmt = (
            select(DailyCollectionRunRow)
            .where(DailyCollectionRunRow.status.in_(["pending", "running"]))
            .order_by(DailyCollectionRunRow.created_at.desc())
            .limit(1)
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def list_recent_runs(self, session: AsyncSession, *, limit: int = 20) -> list[DailyCollectionRunRow]:
        stmt = select(DailyCollectionRunRow).order_by(DailyCollectionRunRow.created_at.desc()).limit(limit)
        return list((await session.execute(stmt)).scalars().all())


class UserRepository:
    async def create_user(
        self, session: AsyncSession, *, username: str, password_hash: str, role: str
    ) -> UserRow:
        """Raises `sqlalchemy.exc.IntegrityError` on a duplicate username -
        the unique constraint is the source of truth, not a pre-check
        (avoids a check-then-insert race)."""
        row = UserRow(username=username, password_hash=password_hash, role=role)
        session.add(row)
        await session.flush()
        return row

    async def get_by_username(self, session: AsyncSession, username: str) -> UserRow | None:
        stmt = select(UserRow).where(UserRow.username == username)
        return (await session.execute(stmt)).scalar_one_or_none()
