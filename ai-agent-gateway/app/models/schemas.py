from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class Intent(str, Enum):
    weather = 'weather'
    calculation = 'calculation'
    internet = 'internet'
    llm = 'llm'


class AgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    user_id: str | None = None
    preferred_model: str | None = None


class ToolCallRecord(BaseModel):
    tool_name: str
    input: dict[str, Any]
    output: dict[str, Any] | str


class AgentResponse(BaseModel):
    answer: str
    intent: Intent
    model: str | None = None
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
