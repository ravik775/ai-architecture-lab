"""Read-side of `weather_observations` - paginated, bounded-range history
queries. Writes to this table happen only via `BatchService` (Phase 6);
the on-demand current-weather path never writes here (see architecture
notes: DB writes are batch-only, keeping the read path free of I/O beyond
cache + provider)."""
from __future__ import annotations

from datetime import date

from app.infrastructure.database.models import WeatherObservationRow
from app.infrastructure.database.repositories import ObservationRepository
from app.infrastructure.database.session import Database


class DateRangeTooLargeError(ValueError):
    pass


class HistoryService:
    def __init__(
        self, db: Database, repository: ObservationRepository, *, max_range_days: int, max_page_size: int
    ) -> None:
        self._db = db
        self._repository = repository
        self._max_range_days = max_range_days
        self._max_page_size = max_page_size

    async def list_history(
        self,
        *,
        location_id: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[WeatherObservationRow], int, int]:
        page_size = min(page_size, self._max_page_size)
        page = max(page, 1)

        if start_date and end_date:
            if end_date < start_date:
                raise ValueError("end_date must not be before start_date")
            if (end_date - start_date).days > self._max_range_days:
                raise DateRangeTooLargeError(
                    f"Date range exceeds the maximum of {self._max_range_days} days"
                )

        offset = (page - 1) * page_size
        async with self._db.session() as session:
            rows, total = await self._repository.list_history(
                session,
                location_id=location_id,
                start_date=start_date,
                end_date=end_date,
                limit=page_size,
                offset=offset,
            )
        return rows, total, page_size
