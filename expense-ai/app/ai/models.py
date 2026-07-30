import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar, Type
from uuid import UUID
from pydantic import BaseModel
from app.schemas import AppRequest

TAppRequest = TypeVar("TAppRequest", bound=AppRequest)
TResponse = TypeVar("TResponse", bound=BaseModel)

class PromptType(str, Enum):
    SUMMARY = "summary"


class AIRequest(BaseModel, Generic[TAppRequest]):
    request: TAppRequest
    prompt: str | None = None
    prompt_type: PromptType

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

@dataclass(frozen=True)
class PromptOptions:
    require_json_output: bool = True
    include_examples: bool = False


@dataclass(slots=True)
class ExecutionContext(Generic[TResponse]):
    """
        Runtime metadata for a single AI execution.

        This object should NEVER contain business data.
        It only tracks runtime execution state.
    """
    response_model: TResponse = None
    provider: Provider = None
    prompt: str | None = None
    request: AIRequest | None = None
    execution_id: UUID = field(default_factory=uuid.uuid4)
    started_at: datetime = field(default_factory=datetime.now)
    attempt: int = 0
    provider_index: int = 0



@dataclass(slots=True)
class ProviderResponse(Generic[TResponse])  :
    """
    Provider-neutral response returned by all LLM providers.

    Runtime owns observability.
    Providers only return execution facts.
    """
    # AI Model
    provider: str
    model: str
    latency_ms: float
    # Response
    content: str | None = None
    parsed: TResponse | None  = None
    # Observability
    usage: TokenUsage | None = None
    metadata: dict[str, Any] = field(default_factory=dict)



@dataclass
class CacheEntry(Generic[TResponse]):
    response: ProviderResponse[TResponse]
    expires_at: datetime
