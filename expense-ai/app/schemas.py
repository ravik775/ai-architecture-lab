from datetime import datetime, timezone, timedelta
from typing import List, Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, AfterValidator


def validate_not_in_future( value: datetime) -> datetime:
    # Use timezone.utc if your datetimes are timezone-aware
    if value > (datetime.now(timezone.utc) + timedelta(seconds=5)):
        raise ValueError("Timestamp cannot be in the future")
    return value

NotFutureDatetime = Annotated[datetime, AfterValidator(validate_not_in_future)]

class Expense(BaseModel):
    description: str = Field(min_length=3, max_length=100)
    amount: float = Field(gt=0)
    quantity: int = Field(gt=0, default=1)
    expense_date: NotFutureDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expense_id: UUID | None = None
    merchant: str | None = None
    category: str | None = None
    notes: str | None = None

class ExpenseRequest(BaseModel):
    submitted_by: str = Field(min_length=3, max_length=100)
    currency: str = Field(min_length=3, max_length=3, default="INR")
    submitted_date: NotFutureDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expenses: List[Expense] = Field(default_factory=list)


class ExpenseResponse(BaseModel):
    tenant: str
    analysis_id: UUID = Field(default_factory=uuid4)
    total_expenses: int
    total_amount: float
    currency: str
    status: str
    summary: str = ""
    suspicious: list[str] = Field(default_factory=list)

