from fastapi import APIRouter, Depends, HTTPException
from app.schemas import ExpenseRequest, ExpenseResponse, ApprovalActionPayload
from app.services.expense_service import ExpenseService
from app.dependencies import get_expense_service

router = APIRouter(prefix="/api/v1/expenses", tags=["Expenses"])

@router.post("/analyze", response_model=ExpenseResponse)
def analyze_expenses(request: ExpenseRequest,  service: ExpenseService = Depends(get_expense_service)) -> ExpenseResponse:
    return service.analyze(request)


@router.post("/{analysis_id}/approve", response_model=ExpenseResponse)
def approve_expense(analysis_id: str, payload: ApprovalActionPayload,
                    service: ExpenseService = Depends(get_expense_service)) -> ExpenseResponse:
    # Safely handles whether ExpenseApprovalGraph wrapper is active or disabled
    if hasattr(service, "resume_approval"):
        return service.resume_approval(analysis_id, payload.action)

    raise HTTPException(
        status_code=400,
        detail="Approval graph workflow is disabled in configuration."
    )