from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_location_service
from app.api.v1.schemas import CountryOut, LocationOut, StateOut
from app.application.location_service import LocationService

router = APIRouter(prefix="/v1/locations", tags=["locations"])


@router.get("/countries", response_model=list[CountryOut])
async def list_countries(service: LocationService = Depends(get_location_service)) -> list[CountryOut]:
    countries = await service.list_countries()
    return [CountryOut.from_row(c) for c in countries]


@router.get("/states", response_model=list[StateOut])
async def list_states(
    country_code: str = Query(..., min_length=2, max_length=2),
    service: LocationService = Depends(get_location_service),
) -> list[StateOut]:
    states = await service.list_states(country_code.upper())
    return [StateOut.from_row(s) for s in states]


@router.get("", response_model=list[LocationOut])
async def list_locations(
    country_code: str | None = Query(None, min_length=2, max_length=2),
    state_code: str | None = Query(None, min_length=1, max_length=10),
    service: LocationService = Depends(get_location_service),
) -> list[LocationOut]:
    locations = await service.list_locations(
        country_code=country_code.upper() if country_code else None,
        state_code=state_code.upper() if state_code else None,
    )
    return [LocationOut.from_row(loc) for loc in locations]


@router.get("/{location_id}", response_model=LocationOut)
async def get_location(
    location_id: str, service: LocationService = Depends(get_location_service)
) -> LocationOut:
    location = await service.get_location(location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return LocationOut.from_row(location)
