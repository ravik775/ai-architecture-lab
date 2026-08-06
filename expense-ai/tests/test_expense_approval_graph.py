from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.agents.expense_approval_graph import ExpenseApprovalGraph
from app.dependencies import get_expense_service
from app.main import app
from app.schemas import Expense, ExpenseRequest, ExpenseResponse
from app.services.expense_service import ExpenseService


class MockExpenseServiceImpl(ExpenseService):
    def __init__(
        self,
        requires_approval: bool = False,
        total_amount: float = 500.0,
        policy_flags: list[str] | None = None,
        suspicious: list[str] | None = None,
    ):
        self.requires_approval = requires_approval
        self.total_amount = total_amount
        self.policy_flags = policy_flags or []
        self.suspicious = suspicious or []

    def analyze(
        self,
        request: ExpenseRequest,
        analysis_id: UUID | None = None,
    ) -> ExpenseResponse:
        return ExpenseResponse(
            tenant="Guest",
            analysis_id=analysis_id or uuid4(),
            status="ANALYZED",
            total_expenses=len(request.expenses),
            total_amount=self.total_amount,
            currency=request.currency,
            summary="Mock expense analysis.",
            largest_category="Travel",
            policy_flags=self.policy_flags,
            requires_approval=self.requires_approval,
            suspicious=self.suspicious,
        )


def test_low_risk_expense_is_auto_approved():
    mock_service = MockExpenseServiceImpl(
        requires_approval=False,
        total_amount=500.0,
        policy_flags=[],
        suspicious=[],
    )

    graph = ExpenseApprovalGraph(expense_service=mock_service)

    response = graph.analyze(_expense_request())

    assert response.status == "APPROVED"
    assert response.total_amount == 500.0
    assert response.requires_approval is False
    assert response.policy_flags == []
    assert response.suspicious == []


def test_high_amount_expense_requires_approval_even_without_ai_flags():
    mock_service = MockExpenseServiceImpl(
        requires_approval=False,
        total_amount=15000.0,
        policy_flags=[],
        suspicious=[],
    )

    graph = ExpenseApprovalGraph(expense_service=mock_service)

    response = graph.analyze(_expense_request())

    assert response.status == "APPROVAL_REQUIRED"
    assert response.total_amount == 15000.0

    resumed = graph.resume_approval(
        analysis_id=str(response.analysis_id),
        action="APPROVED",
    )

    assert resumed.status == "APPROVED"


def test_requires_approval_flag_routes_to_manual_approval():
    mock_service = MockExpenseServiceImpl(
        requires_approval=True,
        total_amount=500.0,
        policy_flags=[],
        suspicious=[],
    )

    graph = ExpenseApprovalGraph(expense_service=mock_service)

    response = graph.analyze(_expense_request())

    assert response.status == "APPROVAL_REQUIRED"

    resumed = graph.resume_approval(
        analysis_id=str(response.analysis_id),
        action="APPROVED",
    )

    assert resumed.status == "APPROVED"


def test_policy_flags_route_to_manual_approval():
    mock_service = MockExpenseServiceImpl(
        requires_approval=False,
        total_amount=500.0,
        policy_flags=[
            "Hotel Approval Policy: Hotel amount requires approval review."
        ],
        suspicious=[],
    )

    graph = ExpenseApprovalGraph(expense_service=mock_service)

    response = graph.analyze(_expense_request())

    assert response.status == "APPROVAL_REQUIRED"

    resumed = graph.resume_approval(
        analysis_id=str(response.analysis_id),
        action="APPROVED",
    )

    assert resumed.status == "APPROVED"


def test_suspicious_expense_routes_to_manual_approval():
    mock_service = MockExpenseServiceImpl(
        requires_approval=False,
        total_amount=500.0,
        policy_flags=[],
        suspicious=[
            "Duplicate expense detected for same merchant and amount."
        ],
    )

    graph = ExpenseApprovalGraph(expense_service=mock_service)

    response = graph.analyze(_expense_request())

    assert response.status == "APPROVAL_REQUIRED"

    resumed = graph.resume_approval(
        analysis_id=str(response.analysis_id),
        action="APPROVED",
    )

    assert resumed.status == "APPROVED"


def test_multi_instance_simulation_with_resume():
    mock_service = MockExpenseServiceImpl(
        requires_approval=True,
        total_amount=15000.0,
    )

    instance_a = ExpenseApprovalGraph(expense_service=mock_service)

    response = instance_a.analyze(_expense_request())
    assert response.status == "APPROVAL_REQUIRED"

    analysis_id = str(response.analysis_id)

    instance_b = ExpenseApprovalGraph(expense_service=mock_service)

    resumed = instance_b.resume_approval(
        analysis_id=analysis_id,
        action="APPROVED",
    )

    assert resumed.status == "APPROVED"


def test_restart_resiliency_rejection_flow():
    mock_service = MockExpenseServiceImpl(
        requires_approval=True,
        total_amount=12000.0,
    )

    graph_before_restart = ExpenseApprovalGraph(expense_service=mock_service)

    response = graph_before_restart.analyze(_expense_request())
    assert response.status == "APPROVAL_REQUIRED"

    analysis_id = str(response.analysis_id)

    graph_after_restart = ExpenseApprovalGraph(expense_service=mock_service)

    final_response = graph_after_restart.resume_approval(
        analysis_id=analysis_id,
        action="REJECTED",
    )

    assert final_response.status == "REJECTED"


def test_analyze_endpoint_can_use_swappable_expense_service():
    mock_service = MockExpenseServiceImpl(
        requires_approval=False,
        total_amount=500.0,
        policy_flags=[],
        suspicious=[],
    )

    app.dependency_overrides[get_expense_service] = lambda: ExpenseApprovalGraph(
        expense_service=mock_service
    )

    try:
        response = TestClient(app).post(
            "/api/v1/expenses/analyze",
            json={
                "submitted_by": "Ravi",
                "currency": "INR",
                "expenses": [
                    {
                        "description": "Hotel stay",
                        "amount": 500,
                        "quantity": 1,
                        "merchant": "Hotel ABC",
                        "category": "Travel",
                    }
                ],
            },
        )

        assert response.status_code == 200

        payload = response.json()

        assert payload["status"] == "APPROVED"
        assert payload["total_amount"] == 500.0
        assert payload["currency"] == "INR"

    finally:
        app.dependency_overrides.clear()


def _expense_request() -> ExpenseRequest:
    return ExpenseRequest(
        submitted_by="Ravi",
        currency="INR",
        expenses=[
            Expense(
                description="Hotel stay",
                amount=500,
                quantity=1,
                merchant="Hotel ABC",
                category="Travel",
            )
        ],
    )