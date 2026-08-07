"""LangGraph node functions - app/llm/chain.py. litellm is monkeypatched,
never calls the real network."""
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.llm import chain as chain_module
from app.llm.memory import store


@pytest.fixture(autouse=True)
def _clean_memory_store():
    # The store is a process-wide singleton (app/llm/memory.py) - clear
    # any session used in this file before and after each test so tests
    # can't see each other's history.
    yield
    for session_id in ("chain-test-session", "chain-test-session-2"):
        store.clear(session_id)


def _settings() -> Settings:
    return Settings(openrouter_api_key="x", openrouter_model="openrouter/test-model")


def _fake_response(content="Hello!", finish_reason="stop", prompt_tokens=10, completion_tokens=4):
    return SimpleNamespace(
        model="openrouter/test-model",
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


# ------------------------------------------------------- _node_load_memory --
def test_load_memory_builds_system_plus_history_plus_user_message():
    store.append("chain-test-session", "user", "earlier question")
    store.append("chain-test-session", "assistant", "earlier answer")

    state = chain_module._node_load_memory(
        {"session_id": "chain-test-session", "user_message": "new question"}
    )

    assert state["history"][0]["content"] == "earlier question"
    roles = [m["role"] for m in state["llm_messages"]]
    assert roles[0] == "system"
    assert state["llm_messages"][-1] == {"role": "user", "content": "new question"}
    assert "earlier answer" in [m["content"] for m in state["llm_messages"]]


def test_load_memory_empty_history_still_has_system_and_user():
    state = chain_module._node_load_memory(
        {"session_id": "chain-test-session-2", "user_message": "hi"}
    )
    assert len(state["llm_messages"]) == 2  # system + user, no history


# ------------------------------------------------------ _node_llm_generate --
def test_llm_generate_populates_state_from_litellm_response(monkeypatch):
    monkeypatch.setattr(chain_module.litellm, "completion", lambda **kw: _fake_response())
    monkeypatch.setattr(chain_module.litellm, "completion_cost", lambda **kw: 0.0025)

    state = chain_module._node_llm_generate(
        {"session_id": "s", "llm_messages": [{"role": "user", "content": "hi"}]},
        _settings(),
    )

    assert state["assistant_message"] == "Hello!"
    assert state["model"] == "openrouter/test-model"
    assert state["prompt_tokens"] == 10
    assert state["completion_tokens"] == 4
    assert state["total_tokens"] == 14
    assert state["cost_usd"] == 0.0025
    assert state["finish_reason"] == "stop"
    assert state["latency_ms"] >= 0


def test_llm_generate_cost_lookup_failure_is_non_fatal(monkeypatch):
    monkeypatch.setattr(chain_module.litellm, "completion", lambda **kw: _fake_response())

    def boom(**kw):
        raise RuntimeError("no pricing data for this model")

    monkeypatch.setattr(chain_module.litellm, "completion_cost", boom)

    state = chain_module._node_llm_generate(
        {"session_id": "s", "llm_messages": [{"role": "user", "content": "hi"}]},
        _settings(),
    )
    assert state["assistant_message"] == "Hello!"  # still succeeds
    assert state["cost_usd"] == 0.0  # best-effort cost lookup, defaults to 0


def test_llm_generate_propagates_completion_errors(monkeypatch):
    def boom(**kw):
        raise RuntimeError("upstream 500")

    monkeypatch.setattr(chain_module.litellm, "completion", boom)

    with pytest.raises(RuntimeError, match="upstream 500"):
        chain_module._node_llm_generate(
            {"session_id": "s", "llm_messages": [{"role": "user", "content": "hi"}]},
            _settings(),
        )


# ---------------------------------------------------- _node_persist_memory --
def test_persist_memory_appends_both_turns():
    state = {
        "session_id": "chain-test-session",
        "user_message": "the question",
        "assistant_message": "the answer",
    }
    chain_module._node_persist_memory(state)

    history = store.get_history("chain-test-session")
    assert [h["role"] for h in history] == ["user", "assistant"]
    assert history[0]["content"] == "the question"
    assert history[1]["content"] == "the answer"


# ------------------------------------------------------- ChatGraphRunner --
def test_chat_graph_runner_end_to_end(monkeypatch):
    fake = lambda **kw: _fake_response(content="graph works")  # noqa: E731
    monkeypatch.setattr(chain_module.litellm, "completion", fake)
    monkeypatch.setattr(chain_module.litellm, "completion_cost", lambda **kw: 0.001)

    runner = chain_module.ChatGraphRunner(_settings())
    result = runner.run("chain-test-session", "does the graph work?")

    assert result["assistant_message"] == "graph works"
    # persisted as a side effect of running the full graph
    history = store.get_history("chain-test-session")
    assert history[-1]["content"] == "graph works"
