from app.ai.models import ExecutionContext, PromptOptions
from app.ai.policies.base import ExecutionHandler, Policy
from app.config import settings
from app.prompts.registry import PromptRegistry
from app.observability.logging import log_info


class PromptPreparationPolicy(Policy):
    """
    Builds the provider-aware AI request after a provider has been selected.

    Responsibilities:
        • Resolve the PromptBuilder
        • Configure PromptOptions
        • Render the prompt
        • Populate context.ai_request

    This policy does NOT communicate with the provider.
    """

    priority = 16
    name = "prompt_preparation"

    def execute(self, context: ExecutionContext, next_handler: ExecutionHandler):
        if context.provider is None:
            raise RuntimeError("Provider must be selected before PromptPreparationPolicy.")

        request = context.request
        prompt_builder = PromptRegistry.get(request.prompt_type)
        if prompt_builder is None:
            raise RuntimeError(f"No PromptBuilder registered for '{request.prompt_type}'.")

        options = PromptOptions(
            include_examples=settings.runtime.include_examples,
        )
        request.prompt = prompt_builder.build(request.request, options)
        log_info("Prompt Generated.", prompt=request.prompt)
        return next_handler()