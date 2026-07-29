from abc import ABC, abstractmethod
from typing import Callable
import logging
from app.ai.models import ExecutionContext
from app.ai.models import ProviderResponse, ResponseModel

ExecutionHandler = Callable[[], ProviderResponse[ResponseModel]]

class Policy(ABC):
    """
    Base class for runtime policies.

    Policies decorate execution rather than exposing
    before()/after() hooks.
    """
    priority: int = 100
    name: str = 'policy'
    registry: dict[str, type["Policy"]] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__()
        Policy.registry[cls.name] = cls
        print(f"Registered {cls.name} policy")

    @abstractmethod
    def execute(self, context: ExecutionContext, next_handler: ExecutionHandler) -> ProviderResponse[ResponseModel]:
        pass