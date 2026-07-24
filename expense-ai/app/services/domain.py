from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from uuid import UUID
from datetime import datetime, timezone, timedelta
from app.schemas import Expense

class ExpenseAnalysis(BaseModel):
    analysis_id: UUID
    tenant: str
    submitted_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    submitted_by: str
    currency: str
    expenses: list[Expense]

    @field_validator("submitted_date")
    @classmethod
    def validate_not_in_future(cls, value: datetime) -> datetime:
        # Use timezone.utc if your datetimes are timezone-aware
        if value > (datetime.now(timezone.utc)+timedelta(seconds=5)):
            raise ValueError("Timestamp cannot be in the future")
        return value

class AIAnalysis(BaseModel):
    summary: str
    categories: list[str]
    suspicious: list[str]