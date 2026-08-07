from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.agent.schemas import AgentQueryResult
from app.domain.errors import AgentTimeoutError

router = APIRouter(prefix="/v1/agent", tags=["agent"])


class AgentQueryRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class AgentQueryResponse(AgentQueryResult):
    duration_ms: float
    tool_calls_invoked: list[str] = Field(default_factory=list)


@router.post("/query", response_model=AgentQueryResponse)
async def agent_query(payload: AgentQueryRequest, request: Request) -> AgentQueryResponse:
    agent_service = request.app.state.agent_service
    try:
        outcome = await agent_service.query(payload.message)
    except AgentTimeoutError as exc:
        raise HTTPException(status_code=504, detail="Agent did not respond within its latency budget") from exc
    except Exception as exc:  # noqa: BLE001 - never leak internal/model errors to the client
        raise HTTPException(status_code=502, detail="Agent failed to produce a response") from exc

    return AgentQueryResponse(
        **outcome.result.model_dump(),
        duration_ms=round(outcome.duration_ms, 2),
        tool_calls_invoked=outcome.tool_calls,
    )
