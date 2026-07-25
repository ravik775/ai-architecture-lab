from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar
from pydantic import BaseModel
T = TypeVar("T", bound=BaseModel)

class AIRequest(BaseModel):
    prompt: str

class AIResponse(BaseModel):
    content: str

@dataclass(slots=True)
class ProviderResponse(Generic[T])  :
    """
    Provider-neutral response returned by all LLM providers.

    Runtime owns observability.
    Providers only return execution facts.
    """

    content: T
    provider: str
    model: str
    latency_ms: float
    usage: dict[str, int] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)