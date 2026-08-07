"""Location discovery: countries -> states -> configured locations.

Thin orchestration over `LocationRepository`. Used by both the REST API
and the PydanticAI agent tools - never by the UI directly (UI calls this
same service, in-process).
"""
from __future__ import annotations

from app.infrastructure.database.models import ConfiguredLocationRow, CountryRow, StateRow
from app.infrastructure.database.repositories import LocationRepository
from app.infrastructure.database.session import Database


class LocationService:
    def __init__(self, db: Database, repository: LocationRepository) -> None:
        self._db = db
        self._repository = repository

    async def list_countries(self) -> list[CountryRow]:
        async with self._db.session() as session:
            return await self._repository.list_countries(session)

    async def list_states(self, country_code: str) -> list[StateRow]:
        async with self._db.session() as session:
            return await self._repository.list_states(session, country_code=country_code)

    async def list_locations(
        self, *, country_code: str | None = None, state_code: str | None = None
    ) -> list[ConfiguredLocationRow]:
        async with self._db.session() as session:
            return await self._repository.list_locations(
                session, country_code=country_code, state_code=state_code
            )

    async def get_location(self, location_id: str) -> ConfiguredLocationRow | None:
        async with self._db.session() as session:
            location = await self._repository.get_location(session, location_id)
            if location is None or not location.active:
                return None
            return location

    async def get_representative_location(
        self, *, country_code: str, state_code: str
    ) -> ConfiguredLocationRow | None:
        async with self._db.session() as session:
            return await self._repository.get_representative_location(
                session, country_code=country_code, state_code=state_code
            )

    async def search_locations_by_name(self, query: str, *, limit: int = 10) -> list[ConfiguredLocationRow]:
        async with self._db.session() as session:
            return await self._repository.search_locations_by_name(session, query, limit=limit)

    async def list_daily_collection_locations(self) -> list[ConfiguredLocationRow]:
        async with self._db.session() as session:
            return await self._repository.list_daily_collection_locations(session)
