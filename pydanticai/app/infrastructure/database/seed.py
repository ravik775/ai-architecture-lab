"""Idempotent seed data: 4 countries, 14 states/cantons, 15 configured
locations (5 India, 5 US, 4 Switzerland + 1 Liechtenstein).

Run with: `uv run python -m app.infrastructure.database.seed`
Safe to re-run - all writes are UPSERTs.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.infrastructure.database.models import ConfiguredLocationRow, CountryRow, StateRow
from app.infrastructure.database.session import Database

logger = logging.getLogger(__name__)

COUNTRIES = [
    {"country_code": "IN", "country_name": "India", "active": True},
    {"country_code": "US", "country_name": "United States", "active": True},
    {"country_code": "CH", "country_name": "Switzerland", "active": True},
    {"country_code": "LI", "country_name": "Liechtenstein", "active": True},
]

# (country_code, state_code, state_name, representative_location_id)
STATES = [
    ("IN", "TG", "Telangana", "hyderabad"),
    ("IN", "MH", "Maharashtra", "mumbai"),
    ("IN", "DL", "Delhi", "delhi"),
    ("IN", "KA", "Karnataka", "bengaluru"),
    ("IN", "TN", "Tamil Nadu", "chennai"),
    ("US", "NY", "New York", "new-york-city"),
    ("US", "CA", "California", "los-angeles"),
    ("US", "IL", "Illinois", "chicago"),
    ("US", "TX", "Texas", "austin"),
    ("US", "WA", "Washington", "seattle"),
    ("CH", "ZH", "Zurich", None),
    ("CH", "GE", "Geneva", None),
    ("CH", "BE", "Bern", "bern"),
    ("CH", "TI", "Ticino", None),
]

# location_id, name, country, state_code, state_name, lat, lon, tz, provider_pref, is_representative
LOCATIONS = [
    ("hyderabad", "Hyderabad", "IN", "TG", "Telangana", 17.3850, 78.4867, "Asia/Kolkata", "open_meteo", True),
    ("mumbai", "Mumbai", "IN", "MH", "Maharashtra", 19.0760, 72.8777, "Asia/Kolkata", "open_meteo", True),
    ("delhi", "Delhi", "IN", "DL", "Delhi", 28.6139, 77.2090, "Asia/Kolkata", "open_meteo", True),
    ("bengaluru", "Bengaluru", "IN", "KA", "Karnataka", 12.9716, 77.5946, "Asia/Kolkata", "open_meteo", True),
    ("chennai", "Chennai", "IN", "TN", "Tamil Nadu", 13.0827, 80.2707, "Asia/Kolkata", "open_meteo", True),
    ("new-york-city", "New York City", "US", "NY", "New York", 40.7128, -74.0060, "America/New_York", "open_meteo", True),
    ("los-angeles", "Los Angeles", "US", "CA", "California", 34.0522, -118.2437, "America/Los_Angeles", "open_meteo", True),
    ("chicago", "Chicago", "US", "IL", "Illinois", 41.8781, -87.6298, "America/Chicago", "open_meteo", True),
    ("austin", "Austin", "US", "TX", "Texas", 30.2672, -97.7431, "America/Chicago", "open_meteo", True),
    ("seattle", "Seattle", "US", "WA", "Washington", 47.6062, -122.3321, "America/Los_Angeles", "open_meteo", True),
    ("zurich", "Zurich", "CH", "ZH", "Zurich", 47.3769, 8.5417, "Europe/Zurich", "meteoswiss", False),
    ("geneva", "Geneva", "CH", "GE", "Geneva", 46.2044, 6.1432, "Europe/Zurich", "meteoswiss", False),
    ("bern", "Bern", "CH", "BE", "Bern", 46.9480, 7.4474, "Europe/Zurich", "meteoswiss", True),
    ("lugano", "Lugano", "CH", "TI", "Ticino", 46.0037, 8.9511, "Europe/Zurich", "meteoswiss", False),
    ("vaduz", "Vaduz", "LI", None, None, 47.1410, 9.5209, "Europe/Vaduz", "meteoswiss", False),
]


async def _upsert_countries(session: AsyncSession) -> None:
    for c in COUNTRIES:
        stmt = sqlite_insert(CountryRow).values(**c)
        stmt = stmt.on_conflict_do_update(index_elements=["country_code"], set_=c)
        await session.execute(stmt)


async def _upsert_locations(session: AsyncSession) -> None:
    for (loc_id, name, country, state_code, state_name, lat, lon, tz, pref, is_rep) in LOCATIONS:
        values = dict(
            location_id=loc_id,
            location_name=name,
            location_type="city",
            country_code=country,
            country_name=next(c["country_name"] for c in COUNTRIES if c["country_code"] == country),
            state_code=state_code,
            state_name=state_name,
            latitude=lat,
            longitude=lon,
            timezone=tz,
            provider_preference=pref,
            active=True,
            daily_collection_enabled=True,
            is_state_representative=is_rep,
        )
        stmt = sqlite_insert(ConfiguredLocationRow).values(**values)
        update_cols = {k: v for k, v in values.items() if k != "location_id"}
        stmt = stmt.on_conflict_do_update(index_elements=["location_id"], set_=update_cols)
        await session.execute(stmt)


async def _upsert_states(session: AsyncSession) -> None:
    for country_code, state_code, state_name, rep_location_id in STATES:
        values = dict(
            country_code=country_code,
            state_code=state_code,
            state_name=state_name,
            representative_location_id=rep_location_id,
            active=True,
        )
        stmt = sqlite_insert(StateRow).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["country_code", "state_code"],
            set_={"state_name": state_name, "representative_location_id": rep_location_id, "active": True},
        )
        await session.execute(stmt)


async def seed() -> None:
    settings = get_settings()
    db = Database(settings.database)
    async with db.session() as session:
        await _upsert_countries(session)
        # Locations first: states.representative_location_id has an FK to
        # configured_locations, so locations must exist before states
        # reference them.
        await _upsert_locations(session)
        await _upsert_states(session)
        await session.commit()
    await db.dispose()
    logger.info("Seed complete: %d countries, %d states, %d locations", len(COUNTRIES), len(STATES), len(LOCATIONS))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed())
