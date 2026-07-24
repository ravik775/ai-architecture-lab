from datetime import datetime, timezone

from app.llm.base import LLMService
from app.llm.mockllm_service import MockLLMService
from app.schemas import Expense, ExpenseRequest
from app.services.expense_service import ExpenseService


def test_expense_service_analyze():
    service = ExpenseService(llm_service=MockLLMService())

    request = ExpenseRequest(
        submitted_by="Jane Smith",
        currency="USD",
        submitted_date=datetime.now(timezone.utc),
        expenses=[
            Expense(description="Cloud Hosting", amount=200.0, quantity=1),
            Expense(description="Domain Registration", amount=100.0, quantity=1),
        ],
    )

    response = service.analyze(request)

    assert response.tenant == "Guest"
    assert response.total_expenses == 2
    assert response.total_amount == 300.0
    assert response.currency == "USD"
    assert response.status == "ANALYZED"
    assert response.summary == "Expenses analyzed successfully."