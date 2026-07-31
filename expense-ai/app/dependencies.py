from fastapi import Depends

from app.agents.expense_approval_graph import ExpenseApprovalGraph
from app.ai.runtime import AIRuntime
from app.config import settings
from app.llm.base import LLMService
from app.services.expense_service import ExpenseService, ExpenseServiceImpl
from app.llm.factory import LLMFactory

def get_llm_service()->LLMService:
    return LLMFactory.create()

def get_expense_service(llm: LLMService = Depends(get_llm_service)) -> ExpenseService:
    """
    FastAPI dependency provider.

    Later this can create the service with:
    - LLMService
    - Database
    - Logger
    - Metrics
    """
    expense_service: ExpenseService = ExpenseServiceImpl(AIRuntime(llm))
    return ExpenseApprovalGraph(expense_service) if settings.agentic_expense else expense_service
