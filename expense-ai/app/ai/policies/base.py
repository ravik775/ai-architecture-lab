from abc import ABC, abstractmethod
from typing import Callable

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
    @abstractmethod
    def execute(self, context: ExecutionContext, next_handler: ExecutionHandler) -> ProviderResponse[ResponseModel]:
        pass