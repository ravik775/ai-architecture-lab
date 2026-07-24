from app.prompts.base import PromptBuilder
from app.prompts.formatters import ExpenseTableFormatter
from app.prompts.renderer import PromptRenderer
from app.prompts.template import PromptTemplate
from app.prompts.versions import get_prompt_template, PromptTemplateNames
from app.schemas import ExpenseRequest


SUMMARY_TEMPLATE = PromptTemplate(
    name="expense-summary",
    version="v1",
    template="""
System
------
You are an enterprise expense auditing assistant.

Context
-------
Employee: $employee
Currency: $currency

Expenses
--------
$expenses

Task
----
1. Categorize expenses
2. Summarize spending
3. Identify anomalies
4. Mention largest category

Output
------
Summary

Largest Category

High Value Expenses

Recommendations
""",
)


class ExpenseSummaryPrompt( PromptBuilder):

    def build(self, request: ExpenseRequest) -> str:
        variables = {
            "employee": request.submitted_by,
            "currency": request.currency,
            "expenses": ExpenseTableFormatter.to_markdown(request.expenses)
        }
        template = get_prompt_template(PromptTemplateNames.EXPENSE_SUMMARY, self.version)
        return PromptRenderer.render(template, variables, )