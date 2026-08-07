from __future__ import annotations

from app.agent.agent import AgentQueryOutcome
from app.agent.schemas import AgentQueryResult
from app.domain.errors import AgentTimeoutError


class _FakeAgentService:
    def __init__(self, outcome=None, exc=None) -> None:
        self._outcome = outcome
        self._exc = exc

    async def query(self, message: str):
        if self._exc:
            raise self._exc
        return self._outcome


def test_agent_query_happy_path(app_client):
    outcome = AgentQueryOutcome(
        result=AgentQueryResult(answer="Sunny in Hyderabad."),
        duration_ms=42.0,
        tool_calls=["resolve_supported_location", "get_current_weather"],
    )
    app_client.app.state.agent_service = _FakeAgentService(outcome=outcome)

    resp = app_client.post("/v1/agent/query", json={"message": "How's the weather in Hyderabad?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "Sunny in Hyderabad."
    assert body["duration_ms"] == 42.0
    assert body["tool_calls_invoked"] == ["resolve_supported_location", "get_current_weather"]


def test_agent_query_timeout_maps_to_504(app_client):
    app_client.app.state.agent_service = _FakeAgentService(exc=AgentTimeoutError("too slow"))
    resp = app_client.post("/v1/agent/query", json={"message": "hello"})
    assert resp.status_code == 504


def test_agent_query_rejects_empty_message(app_client):
    resp = app_client.post("/v1/agent/query", json={"message": ""})
    assert resp.status_code == 422


def test_agent_query_generic_failure_maps_to_502(app_client):
    app_client.app.state.agent_service = _FakeAgentService(exc=RuntimeError("boom"))
    resp = app_client.post("/v1/agent/query", json={"message": "hello"})
    assert resp.status_code == 502
