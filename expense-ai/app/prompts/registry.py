# app/prompts/registry.py

from enum import Enum

from app.prompts.expense_summary import ExpenseSummaryPrompt


class PromptType(str, Enum):
    SUMMARY = "summary"


class PromptRegistry:
    _registry = {
        PromptType.SUMMARY: ExpenseSummaryPrompt(version="v1"),
    }

    @classmethod
    def get(cls, prompt: PromptType):
        try:
            return cls._registry[prompt]
        except KeyError as exc:
            raise KeyError(f"Prompt builder not found: {prompt}") from exc