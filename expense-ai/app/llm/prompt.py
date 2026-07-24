from app.schemas import ExpenseRequest


class ExpensePromptBuilder:
    """Builds prompts for expense-related AI tasks."""
    @staticmethod
    def build_summary_prompt(request: ExpenseRequest) -> str:
        expense_lines = []

        for expense in request.expenses:
            expense_lines.append(
                f"""Description: {expense.description}
                Category: {expense.category}
                Merchant: {expense.merchant}
                Quantity: {expense.quantity}
                Amount: {expense.amount}
                Date: {expense.expense_date}
                """
            )

        prompt = f"""
        You are an expense analysis assistant.

        Submitted By:
        {request.submitted_by}

        Currency:
        {request.currency}

        Expenses:

        {chr(10).join(expense_lines)}

        Provide:
        1. Summary
        2. Total observations
        3. Savings suggestions
        """
        return prompt