from app.ai.runtime import AIRuntime
from app.ai.models import AIRequest
from app.config import settings
from app.observability.logging import log_info
from app.prompts.registry import PromptRegistry, PromptType
from app.schemas import ExpenseRequest, ExpenseResponse, AIExpenseAnalysis

class ExpenseService:
    """Business service responsible for expense analysis."""

    def __init__(self, ai_runtime: AIRuntime):
        self.runtime = ai_runtime

    def analyze(self, request: ExpenseRequest) -> ExpenseResponse:

        total_amount = sum(expense.amount * expense.quantity  for expense in request.expenses )

        log_info(
            "expense.analysis.started",
            submitted_by=request.submitted_by,
            currency=request.currency,
            expense_count=len(request.expenses),
            total_amount=total_amount,
        )

        builder = PromptRegistry.get(PromptType.SUMMARY)
        prompt = builder.build(request)

        ai_request = AIRequest(prompt=prompt)
        ai_analysis = self.runtime.invoke(ai_request, ExpenseResponse)

        log_info(
            "expense.analysis.completed",
            status="ANALYZED",
            suspicious_count=len(ai_analysis.suspicious),
            largest_category=ai_analysis.largest_category,
        )

        return ExpenseResponse(
            tenant="Guest",
            total_expenses=len(request.expenses),
            total_amount=total_amount,
            currency=request.currency,
            status="ANALYZED",
            summary=ai_analysis.summary,
            suspicious=ai_analysis.suspicious,
        )