import  pandas as pd
from app.schemas import ExpenseRequest


class ExpensePromptBuilder:
    """Builds prompts for expense-related AI tasks using modular methods."""

    @staticmethod
    def _build_system_role() -> str:
        return (
            "System\n"
            "-------\n"
            """You are an enterprise expense auditing assistant.

Responsibilities:
- Analyze employee expense reports.
- Categorize expenses.
- Detect unusual spending.
- Never invent missing information.
- Use concise professional business language."""
        )

    @staticmethod
    def _build_business_context(request: ExpenseRequest) -> str:
        return (
            "Context\n"
            "-------\n"
            f"Employee: {request.submitted_by}\n"
            f"Currency: {request.currency}\n"
        )

    @staticmethod
    def _build_expense_section(request: ExpenseRequest) -> str:
        data = [
            {
                "Date": str(expense.expense_date),
                "Merchant": str(expense.merchant),
                "Category": str(expense.category),
                "Description": str(expense.description),
                "Quantity": str(expense.quantity),
                "Amount": str(expense.amount),
            }
            for expense in request.expenses
        ]

        df = pd.DataFrame(data)

        if not df.empty:
            # Using tabulate format if available via pandas, or expanding padding 
            # to ensure clear readability and prevent line-wrapping confusion.
            expense_table = df.to_markdown(index=False, tablefmt="pipe")
        else:
            expense_table = "No expenses recorded."

        return (
            "Expenses:\n"
            "----\n"
            f"{expense_table}\n"
        )

    @staticmethod
    def _build_task_section() -> str:
        return (
            "Task\n"
            "----\n"
            "1. Categorize expenses.\n"
            "2. Summarize spending.\n"
            "3. Identify anomalies.\n"
            "4. Mention largest category.\n"
        )

    @staticmethod
    def _build_output_format() -> str:
        return (
            "Output\n"
            "------\n"
            "Respond in concise business English.\n"
            """
            Format:
            Summary
            Largest Category
            High Value Expenses
            Recommendations
            """
        )

    @classmethod
    def build_summary_prompt(cls, request: ExpenseRequest) -> str:
        """Assembles the full prompts using modular components."""
        prompt_parts = [
            cls._build_system_role(),
            cls._build_business_context(request),
            cls._build_expense_section(request),
            cls._build_task_section(),
            cls._build_output_format(),
        ]

        return "\n".join(prompt_parts)