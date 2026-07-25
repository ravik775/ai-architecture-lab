from fastapi import Depends

from app.llm.base import LLMService
from app.services.expense_service import ExpenseService
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

    return ExpenseService(llm)