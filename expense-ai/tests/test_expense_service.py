import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from app.schemas import ExpenseRequest, ExpenseResponse, Expense, AIExpenseAnalysis
from app.prompts.registry import PromptType
from app.services.expense_service import ExpenseService


@pytest.fixture
def mock_llm_service():
    """Fixture to mock the LLMService dependency with structured chat support."""
    service = MagicMock()
    # Mock structured_chat returning an AIExpenseAnalysis instance
    service.structured_chat.return_value = AIExpenseAnalysis(
        summary="Mocked AI Summary Response",
        largest_category="Travel",
        high_value_expenses=["Hotel - 12000 INR"],
        recommendations=["Validate hotel policy limit."],
        suspicious=[]
    )
    return service


@pytest.fixture
def expense_service(mock_llm_service):
    """Fixture to initialize ExpenseService with a mocked LLM service."""
    return ExpenseService(llm_service=mock_llm_service)


@pytest.fixture
def sample_expense_request():
    """Fixture providing a valid ExpenseRequest sample matching the schema."""
    return ExpenseRequest(
        submitted_by="John Doe",
        currency="INR",
        submitted_date=datetime.now(timezone.utc),
        expenses=[
            Expense(description="Team Lunch", amount=1500.0, quantity=1, category="Food", merchant="Restaurant"),
            Expense(description="Office Supplies", amount=450.0, quantity=2, category="Supplies", merchant="Store"),
        ],
    )


class TestExpenseService:

    @patch("app.services.expense_service.PromptRegistry")
    def test_analyze_success(
            self, mock_prompt_registry, expense_service, mock_llm_service, sample_expense_request
    ):
        """Test successful analysis of expenses, returning correct calculated fields and structured AI response."""
        # Arrange
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Generated Summary Prompt"
        mock_prompt_registry.get.return_value = mock_prompt_builder

        # Act
        response = expense_service.analyze(sample_expense_request)

        # Assert
        # 1. Verify PromptRegistry interaction
        mock_prompt_registry.get.assert_called_once_with(PromptType.SUMMARY)
        mock_prompt_builder.build.assert_called_once_with(sample_expense_request)

        # 2. Verify LLM structured_chat service interaction
        mock_llm_service.structured_chat.assert_called_once_with(
            prompt="Generated Summary Prompt",
            response_model=AIExpenseAnalysis
        )

        # 3. Verify response computations and fields based on the schema
        assert isinstance(response, ExpenseResponse)
        assert response.tenant == "Guest"
        assert response.total_expenses == 2
        # Total amount calculation: (1500.0 * 1) + (450.0 * 2) = 2400.0
        assert response.total_amount == 2400.0
        assert response.currency == "INR"
        assert response.status == "ANALYZED"
        assert response.summary == "Mocked AI Summary Response"
        assert response.suspicious == []

    @patch("app.services.expense_service.PromptRegistry")
    def test_analyze_empty_expenses(
            self, mock_prompt_registry, expense_service, mock_llm_service
    ):
        """Test behavior when the expense request contains no items."""
        # Arrange
        empty_request = ExpenseRequest(
            submitted_by="Jane Doe",
            currency="USD",
            submitted_date=datetime.now(timezone.utc),
            expenses=[]
        )

        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Empty Prompt"
        mock_prompt_registry.get.return_value = mock_prompt_builder

        # Act
        response = expense_service.analyze(empty_request)

        # Assert
        assert response.total_expenses == 0
        assert response.total_amount == 0.0
        assert response.currency == "USD"
        assert response.summary == "Mocked AI Summary Response"
        assert response.suspicious == []