import pytest
from app.prompts.expense_summary import ExpenseSummaryPrompt
from app.prompts.expense_fraud import ExpenseFraudPrompt
from app.prompts.expense_policy import ExpensePolicyPrompt
from app.prompts.expense_categorization import ExpenseCategorizationPrompt
from app.prompts.registry import PromptType, PromptRegistry


# Assuming PromptType and PromptRegistry are imported from your module, e.g.:
# from app.prompt_registry import PromptType, PromptRegistry


class TestPromptRegistry:

    @pytest.mark.parametrize(
        "prompt_type, expected_class",
        [
            (PromptType.SUMMARY, ExpenseSummaryPrompt),
        ],
    )
    def test_get_returns_correct_prompt_instance(self, prompt_type, expected_class):
        """Test that PromptRegistry.get() returns the correct prompt instance for each PromptType."""
        prompt_instance = PromptRegistry.get(prompt_type)

        assert isinstance(prompt_instance, expected_class), (
            f"Expected instance of {expected_class.__name__}, "
            f"got {type(prompt_instance).__name__} for {prompt_type}"
        )

    def test_registry_contains_all_prompt_types(self):
        """Test that the internal registry covers every member of the PromptType enum."""
        for prompt_type in PromptType:
            assert prompt_type in PromptRegistry._registry, (
                f"PromptType.{prompt_type.name} is missing from PromptRegistry._registry"
            )

    def test_get_invalid_prompt_type_raises_key_error(self):
        """Test that passing an invalid or non-existent type raises a KeyError."""
        with pytest.raises(KeyError):
            PromptRegistry.get("invalid_type")  # type: ignore