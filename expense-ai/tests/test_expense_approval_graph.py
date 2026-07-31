# tests/test_expense_approval_graph.py
from datetime import datetime, timezone
from uuid import UUID, uuid4
import pytest
from app.schemas import ExpenseRequest, ExpenseResponse, Expense
from app.agents.expense_approval_graph import ExpenseApprovalGraph
from app.services.expense_service import ExpenseService


class MockExpenseServiceImpl(ExpenseService):
    def __init__(self, requires_approval: bool = False, total_amount: float = 500.0):
        self.requires_approval = requires_approval
        self.total_amount = total_amount

    def analyze(self, request: ExpenseRequest, analysis_id: UUID | None = None) -> ExpenseResponse:
        return ExpenseResponse(
            tenant="Guest",
            status="ANALYZED",
            total_expenses=len(request.expenses),
            total_amount=self.total_amount,
            currency=request.currency,
            requires_approval=self.requires_approval,
            # Generate a new UUID if analysis_id is None
            analysis_id=analysis_id or uuid4()
        )


def test_multi_instance_simulation_with_resume():
    """
    Simulates Instance A receiving initial request and Instance B receiving
    the manual approval resume request.
    """
    mock_service = MockExpenseServiceImpl(requires_approval=True, total_amount=15000.0)

    # Instance A receives initial request
    instance_a = ExpenseApprovalGraph(expense_service=mock_service)

    request = ExpenseRequest(
        submitted_by="John Doe",
        currency="INR",
        expenses=[]
    )

    res_a = instance_a.analyze(request)
    assert res_a.status == "APPROVAL_REQUIRED"
    analysis_id = str(res_a.analysis_id)

    # Instance B receives the resume API call (both share underlying checkpointer)
    instance_b = ExpenseApprovalGraph(expense_service=mock_service)
    res_b = instance_b.resume_approval(analysis_id=analysis_id, action="APPROVED")

    assert res_b.status == "APPROVED"


def test_restart_resiliency_rejection_flow():
    """
    Simulates graph state recovery after service re-instantiation.
    """
    mock_service = MockExpenseServiceImpl(requires_approval=True, total_amount=12000.0)

    graph_before_restart = ExpenseApprovalGraph(expense_service=mock_service)
    request = ExpenseRequest(submitted_by="Jane Doe", currency="USD", expenses=[])

    response = graph_before_restart.analyze(request)
    analysis_id = str(response.analysis_id)

    # Simulate app server restart by creating new graph instance
    graph_after_restart = ExpenseApprovalGraph(expense_service=mock_service)
    final_response = graph_after_restart.resume_approval(analysis_id=analysis_id, action="REJECTED")

    assert final_response.status == "REJECTED"