from app.ai.models import PromptOptions
from app.prompts.base import PromptBuilder
from app.prompts.formatters import ExpenseTableFormatter
from app.prompts.renderer import PromptRenderer
from app.prompts.versions import get_prompt_template, PromptTemplateNames
from app.schemas import ExpenseRequest

class ExpenseSummaryPrompt(PromptBuilder):

    def build(self, request: ExpenseRequest, options: PromptOptions) -> str:
        variables = {
            "employee": request.submitted_by,
            "currency": request.currency,
            "expenses": ExpenseTableFormatter.to_markdown(request.expenses),
            "policy_context": options.policy_context or "No policy context provided."
        }
        template = get_prompt_template(PromptTemplateNames.EXPENSE_SUMMARY, self.version)
        return PromptRenderer.render(template, variables, options)