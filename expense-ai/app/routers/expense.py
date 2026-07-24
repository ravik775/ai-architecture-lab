from fastapi import APIRouter, Depends
from app.schemas import ExpenseRequest, ExpenseResponse
from app.services.expense_service import ExpenseService
from app.dependencies import get_expense_service

router = APIRouter(prefix="/api/v1/expenses", tags=["Expenses"])

@router.post("/analyze", response_model=ExpenseResponse)
def analyze_expenses(request: ExpenseRequest,  service: ExpenseService = Depends(get_expense_service)) -> ExpenseResponse:
    return service.analyze(request)