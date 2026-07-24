from app.schemas import ExpenseRequest, ExpenseResponse
from app.llm.base import LLMService
from app.llm.prompt import ExpensePromptBuilder
import logging

logger = logging.getLogger(__name__)
class ExpenseService:
    """Handles expense analysis business logic. """
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service

    def analyze(self, request: ExpenseRequest) -> ExpenseResponse:
        total_amount = sum(expense.amount for expense in request.expenses)
        prompt = ExpensePromptBuilder.build_summary_prompt(request)
        logger.debug( "Prompt length=%d", len(prompt) )
        ai_summary = self.llm_service.chat(prompt)

        return ExpenseResponse(
            tenant="Guest",
            total_expenses=len(request.expenses),
            total_amount=total_amount,
            currency=request.currency,
            status="ANALYZED",
            summary=ai_summary,
        )