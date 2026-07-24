import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from app.schemas import ExpenseRequest, ExpenseResponse, Expense
from app.prompts.registry import PromptType
from app.services.expense_service import ExpenseService  # Adjust import based on your file structure


@pytest.fixture
def mock_llm_service():
    """Fixture to mock the LLMService dependency."""
    service = MagicMock()
    service.chat.return_value = "Mocked AI Summary Response"
    return service


@pytest.fixture
def expense_service(mock_llm_service):
    """Fixture to initialize ExpenseService with a mocked LLM service."""
    return ExpenseService(llm_service=mock_llm_service)


@pytest.fixture
def sample_expense_request():
    """Fixture providing a valid ExpenseRequest sample matching the updated schema."""
    return ExpenseRequest(
        submitted_by="John Doe",
        currency="INR",
        submitted_date=datetime.now(timezone.utc),
        expenses=[
            Expense(description="Team Lunch", amount=1500.0, quantity=1),
            Expense(description="Office Supplies", amount=450.0, quantity=2),
        ],
    )


class TestExpenseService:

    @patch("app.services.expense_service.PromptRegistry")
    def test_analyze_success(
            self, mock_prompt_registry, expense_service, mock_llm_service, sample_expense_request
    ):
        """Test successful analysis of expenses, returning correct calculated fields and AI response."""
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

        # 2. Verify LLM service interaction
        mock_llm_service.chat.assert_called_once_with("Generated Summary Prompt")

        # 3. Verify response computations and fields based on the new schema
        assert isinstance(response, ExpenseResponse)
        assert response.tenant == "Guest"
        assert response.total_expenses == 2
        # Total amount calculation: (1500.0 * 1) + (450.0 * 2) = 2400.0
        assert response.total_amount == 2400.0
        assert response.currency == "INR"
        assert response.status == "ANALYZED"
        assert response.summary == "Mocked AI Summary Response"
        assert response.analysis_id is not None
        assert response.suspicious == []

    @patch("app.services.expense_service.PromptRegistry")
    def test_analyze_empty_expenses(
            self, mock_prompt_registry, expense_service, mock_llm_service
    ):
        """Test behavior when the expense request contains no items."""
        # Arrange
        empty_request = ExpenseRequest(submitted_by="Jane Doe", currency="USD", expenses=[])

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
        assert response.suspicians == [] if hasattr(response, 'suspicians') else response.suspicious == []