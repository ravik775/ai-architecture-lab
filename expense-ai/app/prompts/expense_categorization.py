from app.prompts.base import PromptBuilder


class ExpenseCategorizationPrompt(
    PromptBuilder,
):

    def build(self, request):

        raise NotImplementedError