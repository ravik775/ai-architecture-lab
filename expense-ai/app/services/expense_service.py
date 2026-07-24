from app.schemas import ExpenseRequest, ExpenseResponse, AIExpenseAnalysis
from app.llm.base import LLMService
import logging
from app.prompts.registry import PromptRegistry, PromptType

logger = logging.getLogger(__name__)
class ExpenseService:
    """Handles expense analysis business logic. """
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service

    def analyze(self, request: ExpenseRequest) -> ExpenseResponse:
        total_amount = sum(exp.amount * exp.quantity for exp in request.expenses)
        builder = PromptRegistry.get(PromptType.SUMMARY)
        prompt = builder.build(request)
        logger.debug("Prompt length=%d\n%s\n", len(prompt), prompt)
        #ai_analysis = self.llm_service.chat(prompt)
        ai_analysis = self.llm_service.structured_chat( prompt=prompt, response_model=AIExpenseAnalysis  )
        logger.debug( "ai_analysis: %s",  ai_analysis )
        return ExpenseResponse(
            tenant="Guest",
            total_expenses=len(request.expenses),
            total_amount=total_amount,
            currency=request.currency,
            status="ANALYZED",
            summary=ai_analysis.summary,
            suspicious=ai_analysis.suspicious,
        )