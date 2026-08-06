from app.ai.models import ExecutionContext, ProviderResponse, TResponse
from app.ai.policies.base import Policy, ExecutionHandler
from app.exceptions import GuardrailViolation


class InputGuardrailPolicy(Policy):
    priority = 18
    name = 'guardrail'
    BLOCKED_PHRASES = (
        "ignore previous instructions",
        "reveal system prompt",
        "act as developer",
    )

    def execute(self, context: ExecutionContext, next_handler: ExecutionHandler) -> ProviderResponse[TResponse]:

        prompt = context.request.prompt.lower()
        for phrase in self.BLOCKED_PHRASES:
            if phrase in prompt:
                raise GuardrailViolation(f"GuardrailViolation: Violation due to phrase {phrase}")

        return next_handler()