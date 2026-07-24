from typing import List

import pandas as pd
from app.schemas import Expense


class ExpenseTableFormatter:

    @staticmethod
    def to_markdown(expenses:  List[Expense] ) -> str:
        rows = []
        for expense in expenses:
            rows.append(
                {
                    "Date": str(expense.expense_date),
                    "Merchant": expense.merchant,
                    "Category": expense.category,
                    "Description": expense.description,
                    "Quantity": expense.quantity,
                    "Amount": expense.amount,
                }
            )

        if not rows:
            return "No expenses."

        return pd.DataFrame(rows).to_markdown(
            index=False,
            tablefmt="pipe",
        )