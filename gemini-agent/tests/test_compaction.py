from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.agent.compaction import maybe_compact_history


def test_short_history_is_not_compacted():
    messages = [HumanMessage(content="hi"), AIMessage(content="hello")]
    result, was_compacted = maybe_compact_history(messages, "gemini/gemini-2.5-flash", "key")
    assert result == messages
    assert was_compacted is False


def test_long_history_gets_compacted():
    # Build enough history to exceed COMPACTION_THRESHOLD_CHARS (10_000).
    messages = []
    for i in range(10):
        messages.append(HumanMessage(content=f"question {i} " + "x" * 1000))
        messages.append(AIMessage(content=f"answer {i} " + "y" * 1000))

    with patch("src.agent.compaction.LiteLLMChatModel") as mock_model_cls:
        mock_llm = mock_model_cls.return_value
        mock_llm.invoke.return_value = AIMessage(content="Summary of prior turns.")

        result, was_compacted = maybe_compact_history(messages, "gemini/gemini-2.5-flash", "key")

    assert was_compacted is True
    assert isinstance(result[0], SystemMessage)
    assert "Summary of prior turns." in result[0].content
    # Recent messages preserved verbatim, older ones summarized away.
    assert result[-1] == messages[-1]
    assert len(result) < len(messages)


def test_compaction_never_splits_a_tool_call_pair():
    messages = [HumanMessage(content="do something " + "x" * 3000)]
    ai_with_tool_call = AIMessage(
        content="",
        tool_calls=[{"name": "some_tool", "args": {}, "id": "call_1", "type": "tool_call"}],
    )
    messages.append(ai_with_tool_call)
    messages.append(ToolMessage(content="tool result " + "z" * 3000, tool_call_id="call_1"))
    messages.append(AIMessage(content="done " + "w" * 3000))
    messages.append(HumanMessage(content="next question " + "v" * 3000))
    messages.append(AIMessage(content="next answer"))

    with patch("src.agent.compaction.LiteLLMChatModel") as mock_model_cls:
        mock_llm = mock_model_cls.return_value
        mock_llm.invoke.return_value = AIMessage(content="Summary.")

        result, was_compacted = maybe_compact_history(messages, "gemini/gemini-2.5-flash", "key")

    if was_compacted:
        # Whatever the cut point, a ToolMessage must never appear as the
        # first "recent" message without its preceding AIMessage.tool_calls.
        recent = result[1:]
        if recent and isinstance(recent[0], ToolMessage):
            raise AssertionError("compaction split a tool-call/tool-result pair")


def test_compaction_failure_falls_back_to_original_messages():
    messages = []
    for i in range(10):
        messages.append(HumanMessage(content=f"question {i} " + "x" * 1000))
        messages.append(AIMessage(content=f"answer {i} " + "y" * 1000))

    with patch("src.agent.compaction.LiteLLMChatModel") as mock_model_cls:
        mock_model_cls.return_value.invoke.side_effect = RuntimeError("provider error")
        result, was_compacted = maybe_compact_history(messages, "gemini/gemini-2.5-flash", "key")

    assert was_compacted is False
    assert result == messages
