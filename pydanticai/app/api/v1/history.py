from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_history_service
from app.api.v1.schemas import HistoryObservationOut, HistoryResponse
from app.application.history_service import DateRangeTooLargeError, HistoryService

router = APIRouter(prefix="/v1/weather", tags=["weather"])


@router.get("/history", response_model=HistoryResponse)
async def get_weather_history(
    location_id: str | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    service: HistoryService = Depends(get_history_service),
) -> HistoryResponse:
    try:
        rows, total, effective_page_size = await service.list_history(
            location_id=location_id,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
        )
    except DateRangeTooLargeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    total_pages = max(1, (total + effective_page_size - 1) // effective_page_size)
    return HistoryResponse(
        items=[HistoryObservationOut.from_row(r) for r in rows],
        total=total,
        page=page,
        page_size=effective_page_size,
        total_pages=total_pages,
    )
