from datetime import datetime, timezone
from app.schemas import ExpenseRequest, Expense
from app.services.expense_service import ExpenseService
from app.llm.factory import LLMFactory


def test_expense_service_analyze():
    # Create the LLM service using the factory (or use a mock instance)
    llm_service = LLMFactory.create()
    service = ExpenseService(llm_service=llm_service)

    request = ExpenseRequest(
        submitted_by="Jane Smith",
        currency="USD",
        submitted_date=datetime.now(timezone.utc),
        expenses=[
            Expense(
                description="Cloud Hosting",
                amount=200.0,
                merchant="AWS",
                category="Infrastructure",
            ),
            Expense(
                description="Domain Registration",
                amount=100.0,
                merchant="Namecheap",
                category="IT",
            ),
        ],
    )

    response = service.analyze(request)

    assert response.tenant == "Guest"
    assert response.total_expenses == 2
    assert response.total_amount == 300.0
    assert response.currency == "USD"
    assert response.status == "ANALYZED"