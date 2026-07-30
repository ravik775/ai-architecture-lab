import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, TypeVar
from uuid import UUID
from pydantic import BaseModel
from app.config import settings

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)

class AIRequest(BaseModel):
    prompt: str

class AIResponse(BaseModel):
    content: str


@dataclass(slots=True)
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    def items(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }

@dataclass(frozen=True, slots=True)
class Provider:
    name: str
    model: str
    api_key: str
    priority: int = 0
    base_url: str | None = None
    enabled: bool = True

@dataclass(slots=True)
class ExecutionContext:
    """
        Runtime metadata for a single AI execution.

        This object should NEVER contain business data.
        It only tracks runtime execution state.
    """
    provider: Provider = None
    prompt: str = None
    execution_id: UUID = field(default_factory=uuid.uuid4)
    started_at: datetime = field(default_factory=datetime.now)
    attempt: int = 0
    provider_index: int = 0

@dataclass(slots=True)
class ProviderResponse(Generic[ResponseModel])  :
    """
    Provider-neutral response returned by all LLM providers.

    Runtime owns observability.
    Providers only return execution facts.
    """

    content: ResponseModel
    provider: str
    model: str
    latency_ms: float
    usage: TokenUsage | None = None
    metadata: dict[str, Any] = field(default_factory=dict)



@dataclass
class CacheEntry:
    response: ProviderResponse[ResponseModel]
    expires_at: datetime
