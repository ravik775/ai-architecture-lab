from abc import ABC
from typing import List, Callable

from app.ai.models import ExecutionContext, ProviderResponse
from app.ai.policies.base import Policy


class Pipeline:
    def __init__(self, policies : List[Policy]):
        self.policies = policies

    def execute(self, context: ExecutionContext, handler: Callable[[], ProviderResponse], ) -> ProviderResponse:
        next_handler = handler
        for policy in reversed(self.policies):
            current = next_handler
            next_handler = lambda p=policy, h=current:p.execute(context, h)
        return next_handler()

