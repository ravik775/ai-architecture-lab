from datetime import datetime, timezone

import pytest

from app.prompts.expense_summary import ExpenseSummaryPrompt
from app.prompts.versions import get_prompt_template, PromptTemplateNames
from app.schemas import Expense, ExpenseRequest


def test_summary_prompt_renders_required_sections():
    request = ExpenseRequest(
        submitted_by="Ravi",
        currency="INR",
        submitted_date=datetime.now(timezone.utc),
        expenses=[
            Expense(
                description="Cloud Hosting",
                amount=2000,
                merchant="AWS",
                category="Infrastructure",
            )
        ],
    )

    prompt = ExpenseSummaryPrompt(version="v1").build(request)

    assert "System" in prompt
    assert "Business Context" in prompt
    assert "Input Data" in prompt
    assert "Task" in prompt
    assert "Expected Output" in prompt
    assert "Ravi" in prompt
    assert "INR" in prompt
    assert "AWS" in prompt
    assert "Cloud Hosting" in prompt


def test_summary_prompt_handles_empty_expenses():
    request = ExpenseRequest(
        submitted_by="Ravi",
        currency="INR",
        expenses=[],
    )

    prompt = ExpenseSummaryPrompt(version="v1").build(request)

    assert "No expenses." in prompt


def test_summary_prompt_includes_few_shot_examples():
    request = ExpenseRequest(
        submitted_by="Ravi",
        currency="INR",
        expenses=[],
    )

    prompt = ExpenseSummaryPrompt(version="v1").build(request)

    assert "Example Input:" in prompt
    assert "Expected Output:" in prompt
    assert "Actual Request:" in prompt


def test_prompt_version_lookup_success():
    template = get_prompt_template(PromptTemplateNames.EXPENSE_SUMMARY, "v1")

    assert template.name == "expense-summary"
    assert template.version == "v1"


def test_prompt_version_lookup_failure():
    with pytest.raises(KeyError):
        get_prompt_template(PromptTemplateNames.EXPENSE_SUMMARY, "v999")