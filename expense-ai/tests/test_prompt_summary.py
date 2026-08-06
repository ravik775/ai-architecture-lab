# tests/test_prompt_registry.py
import pytest
from app.ai.models import PromptType
from app.prompts.expense_summary import ExpenseSummaryPrompt
from app.prompts.registry import PromptRegistry


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