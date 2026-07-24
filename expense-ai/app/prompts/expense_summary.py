from app.prompts.base import PromptBuilder
from app.prompts.formatters import ExpenseTableFormatter
from app.prompts.renderer import PromptRenderer
from app.prompts.versions import get_prompt_template, PromptTemplateNames
from app.schemas import ExpenseRequest

class ExpenseSummaryPrompt( PromptBuilder):

    def build(self, request: ExpenseRequest) -> str:
        variables = {
            "employee": request.submitted_by,
            "currency": request.currency,
            "expenses": ExpenseTableFormatter.to_markdown(request.expenses)
        }
        template = get_prompt_template(PromptTemplateNames.EXPENSE_SUMMARY, self.version)
        return PromptRenderer.render(template, variables, )