from abc import ABC, abstractmethod

from app.schemas import ExpenseRequest


class PromptBuilder(ABC):

    @abstractmethod
    def build(self, request: ExpenseRequest) -> str:
        pass