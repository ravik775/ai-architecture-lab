from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel

from app.infrastructure.database.models import DailyCollectionRunRow
from app.infrastructure.database.utils import as_utc


class DailyCollectionRunOut(BaseModel):
    job_id: str
    scheduled_time: datetime
    start_time: datetime | None
    finish_time: datetime | None
    status: str
    total_location_count: int
    success_count: int
    failure_count: int
    error_summary: list[dict] | None

    @classmethod
    def from_row(cls, row: DailyCollectionRunRow) -> "DailyCollectionRunOut":
        return cls(
            job_id=row.job_id,
            scheduled_time=as_utc(row.scheduled_time),
            start_time=as_utc(row.start_time) if row.start_time else None,
            finish_time=as_utc(row.finish_time) if row.finish_time else None,
            status=row.status,
            total_location_count=row.total_location_count,
            success_count=row.success_count,
            failure_count=row.failure_count,
            error_summary=json.loads(row.error_summary) if row.error_summary else None,
        )
