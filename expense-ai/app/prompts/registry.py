from enum import Enum

from app.prompts.expense_summary import ExpenseSummaryPrompt
from app.prompts.expense_fraud import ExpenseFraudPrompt
from app.prompts.expense_policy import ExpensePolicyPrompt
from app.prompts.expense_categorization import ExpenseCategorizationPrompt


class PromptType(Enum):
    SUMMARY = "summary"
    FRAUD = "fraud"
    POLICY = "policy"
    CATEGORIZATION = "categorization"

class PromptRegistry:

    _registry = {
        PromptType.SUMMARY: ExpenseSummaryPrompt(),
        PromptType.FRAUD:   ExpenseFraudPrompt(),
        PromptType.POLICY:  ExpensePolicyPrompt(),
        PromptType.CATEGORIZATION: ExpenseCategorizationPrompt(),
    }

    @classmethod
    def get(cls, prompt: PromptType ):
        return cls._registry[prompt]