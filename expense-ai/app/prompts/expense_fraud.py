from app.prompts.base import PromptBuilder


class ExpenseFraudPrompt(
    PromptBuilder,
):

    def build(self, request):

        raise NotImplementedError