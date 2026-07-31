import uuid
from abc import ABC, abstractmethod
from uuid import UUID

from app.ai.runtime import AIRuntime
from app.ai.models import AIRequest, PromptType, AIExpenseAnalysis
from app.observability.logging import log_info
from app.schemas import ExpenseRequest, ExpenseResponse
from opentelemetry import trace

class ExpenseService(ABC):
    @abstractmethod
    def analyze(self, request: ExpenseRequest, analysis_id: UUID| None=None) -> ExpenseResponse:
        pass


tracer = trace.get_tracer("expense-ai")
class ExpenseServiceImpl(ExpenseService):
    """Business service responsible for expense analysis."""

    def __init__(self, ai_runtime: AIRuntime):
        self.runtime = ai_runtime

    def analyze(self, request: ExpenseRequest, analysis_id: UUID| None=None) -> ExpenseResponse:
        analysis_id = analysis_id or uuid.uuid4()
        with tracer.start_as_current_span("expense.service.analyze") as span:
            span.set_attribute("expense.count", len(request.expenses))
            span.set_attribute("expense.currency", request.currency)

            total_amount = sum(expense.amount * expense.quantity  for expense in request.expenses )

            log_info(
                "expense.analysis.started",
                submitted_by=request.submitted_by,
                currency=request.currency,
                expense_count=len(request.expenses),
                total_amount=total_amount,
            )
            ai_request = AIRequest[ExpenseRequest](request=request, prompt_type=PromptType.SUMMARY)
            ai_analysis = self.runtime.invoke(ai_request, AIExpenseAnalysis)

            log_info(
                "expense.analysis.completed",
                status="ANALYZED",
                suspicious_count=len(ai_analysis.suspicious),
                largest_category=ai_analysis.largest_category,
            )

            return ExpenseResponse(
                analysis_id=analysis_id,
                tenant="Guest",
                total_expenses=len(request.expenses),
                total_amount=total_amount,
                currency=request.currency,
                status="ANALYZED",
                summary=ai_analysis.summary,
                largest_category=ai_analysis.largest_category,
                policy_flags=ai_analysis.policy_flags,
                requires_approval=ai_analysis.requires_approval,
                suspicious=ai_analysis.suspicious,
            )