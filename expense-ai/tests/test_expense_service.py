# tests/test_expense_service.py
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.ai.models import AIExpenseAnalysis
from app.schemas import Expense, ExpenseRequest, ExpenseResponse
# FIX: Import ExpenseServiceImpl alongside ExpenseService
from app.services.expense_service import ExpenseService, ExpenseServiceImpl


@pytest.fixture
def mock_ai_runtime():
    runtime = MagicMock()
    runtime.invoke.return_value = AIExpenseAnalysis(
        summary="Mocked AI Summary Response",
        largest_category="Travel",
        policy_flags=[
            "Travel Reimbursement Policy: Expense requires business purpose validation."
        ],
        requires_approval=True,
        suspicious=[],
    )
    return runtime


@pytest.fixture
def expense_service(mock_ai_runtime) -> ExpenseService:
    # FIX: Instantiate ExpenseServiceImpl instead of ExpenseService
    return ExpenseServiceImpl(ai_runtime=mock_ai_runtime)


@pytest.fixture
def sample_expense_request():
    return ExpenseRequest(
        submitted_by="John Doe",
        currency="INR",
        submitted_date=datetime.now(timezone.utc),
        expenses=[
            Expense(
                description="Team Lunch",
                amount=1500.0,
                quantity=1,
                category="Food",
                merchant="Restaurant",
            ),
            Expense(
                description="Office Supplies",
                amount=450.0,
                quantity=2,
                category="Supplies",
                merchant="Store",
            ),
        ],
    )


def test_analyze_success(expense_service, mock_ai_runtime, sample_expense_request):
    response = expense_service.analyze(sample_expense_request)

    mock_ai_runtime.invoke.assert_called_once()

    assert isinstance(response, ExpenseResponse)
    assert response.tenant == "Guest"
    assert response.total_expenses == 2
    assert response.total_amount == 2400.0
    assert response.currency == "INR"
    assert response.status == "APPROVED"
    assert response.summary == "Mocked AI Summary Response"
    assert response.largest_category == "Travel"
    assert response.policy_flags == [
        "Travel Reimbursement Policy: Expense requires business purpose validation."
    ]
    assert response.requires_approval is True
    assert response.suspicious == []


def test_analyze_empty_expenses(expense_service, mock_ai_runtime):
    request = ExpenseRequest(
        submitted_by="Jane Doe",
        currency="USD",
        submitted_date=datetime.now(timezone.utc),
        expenses=[],
    )

    response = expense_service.analyze(request)

    mock_ai_runtime.invoke.assert_called_once()

    assert response.total_expenses == 0
    assert response.total_amount == 0.0
    assert response.currency == "USD"
    assert response.summary == "Mocked AI Summary Response"
    assert response.largest_category == "Travel"
    assert response.policy_flags == [
        "Travel Reimbursement Policy: Expense requires business purpose validation."
    ]
    assert response.requires_approval is True
    assert response.suspicious == []