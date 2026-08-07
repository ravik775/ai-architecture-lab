from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.internal.auth import require_internal_token
from app.api.internal.schemas import DailyCollectionRunOut
from app.domain.errors import BatchAlreadyRunningError

router = APIRouter(prefix="/internal/jobs", tags=["internal"], dependencies=[Depends(require_internal_token)])


@router.post("/daily-weather", response_model=DailyCollectionRunOut, status_code=202)
async def trigger_daily_weather_job(request: Request) -> DailyCollectionRunOut:
    settings = request.app.state.settings
    if not settings.scheduler.manual_trigger_enabled:
        raise HTTPException(status_code=403, detail="Manual batch trigger is disabled")

    batch_service = request.app.state.batch_service
    try:
        run = await batch_service.run_daily_collection(trigger_source="manual")
    except BatchAlreadyRunningError as exc:
        raise HTTPException(
            status_code=409, detail=f"A daily collection run is already in progress: {exc.job_id}"
        ) from exc
    return DailyCollectionRunOut.from_row(run)


@router.get("/daily-weather/{job_id}", response_model=DailyCollectionRunOut)
async def get_daily_weather_job(job_id: str, request: Request) -> DailyCollectionRunOut:
    db = request.app.state.db
    job_repository = request.app.state.job_repository
    async with db.session() as session:
        run = await job_repository.get_run(session, job_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return DailyCollectionRunOut.from_row(run)
