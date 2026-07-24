from enum import Enum

from app.prompts.template import FewShotExample, PromptTemplate

EXPENSE_SUMMARY_V1 = PromptTemplate(
    name="expense-summary",
    version="v1",
    examples=[
        FewShotExample(
            input="Employee: Ravi\nCurrency: INR\nExpense: Hotel, Travel, 12000",
            output=(
                '{\n'
                '  "summary": "Travel spending is high.",\n'
                '  "largest_category": "Travel",\n'
                '  "high_value_expenses": ["Hotel - 12000 INR"],\n'
                '  "recommendations": ["Validate hotel policy limit."],\n'
                '  "suspicious": []\n'
                '}'
            ),
        )
    ],
    template="""
System
------
You are an enterprise expense auditing assistant.
Business Context
----------------
Analyze employee expenses for finance review.
Do not invent missing data.
Use concise professional business language.
Input Data
----------
Employee: $employee
Currency: $currency
Expenses:
$expenses
Task
----
1. Categorize expenses.
2. Summarize spending.
3. Identify high-value or unusual expenses.
4. Mention the largest spending category.
5. Give practical recommendations.
Constraints
-----------
- Use only the provided expense data.
- If data is missing, say it is missing.
- Do not assume policy violations unless evidence exists.
- Keep the response concise.
Expected Output
---------------
Return only JSON that matches the configured response schema.
Do not include markdown.
Do not include explanation outside JSON.
All schema fields must be present. Use empty arrays when no items exist.
""",
)
EXPENSE_SUMMARY_V2 = PromptTemplate(
    name="expense-summary",
    version="v2",
    template="""
System
------
You are a senior finance operations analyst.
Business Context
----------------
The business wants quick expense risk visibility.
Input Data
----------
Employee: $employee
Currency: $currency
Expenses:
$expenses
Task
----
Create an executive-friendly expense analysis.
Expected Output
---------------
Return only JSON that matches the configured response schema.
Do not include markdown.
Do not include explanation outside JSON.
All schema fields must be present. Use empty arrays when no items exist.
""",
)

class PromptTemplateNames(str, Enum):
    EXPENSE_SUMMARY = "expense-summary"

PROMPT_VERSIONS = {
    (PromptTemplateNames.EXPENSE_SUMMARY, "v1"): EXPENSE_SUMMARY_V1,
    (PromptTemplateNames.EXPENSE_SUMMARY, "v2"): EXPENSE_SUMMARY_V2,
}


def get_prompt_template(name: PromptTemplateNames, version: str = "v1") -> PromptTemplate:
    try:
        return PROMPT_VERSIONS[(name, version)]
    except KeyError as exc:
        raise KeyError(f"Prompt template not found: {name}:{version}") from exc