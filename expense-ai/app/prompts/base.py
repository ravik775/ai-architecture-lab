from abc import ABC, abstractmethod

from app.ai.models import PromptOptions
from app.schemas import ExpenseRequest


class PromptBuilder(ABC):

    def __init__(self, version: str = "v1"):
        self.version = version

    @abstractmethod
    def build(self, request: ExpenseRequest, options: PromptOptions) -> str:
        pass
