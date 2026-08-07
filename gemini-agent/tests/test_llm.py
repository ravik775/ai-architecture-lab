from src.agent.llm import _extract_fallback_tool_call, is_capacity_error


def test_fallback_extracts_tool_call_from_plain_json_text():
    # Exact shape repeatedly observed from qwen2.5-coder:1.5b via Ollama:
    # the whole response is a clean JSON object naming a real tool, instead
    # of using the API's structured tool-calling mechanism.
    content = """{
  "name": "propose_file_change",
  "arguments": {
    "relative_path": "app/main.py",
    "new_content": "print('hi')",
    "description": "Create main.py"
  }
}"""
    result = _extract_fallback_tool_call(content, {"propose_file_change", "read_file"})
    assert result is not None
    assert result["name"] == "propose_file_change"
    assert result["args"]["relative_path"] == "app/main.py"
    assert result["type"] == "tool_call"
    assert result["id"].startswith("call_")


def test_fallback_accepts_parameters_key_as_alias_for_arguments():
    content = '{"name": "read_file", "parameters": {"relative_path": "x.py"}}'
    result = _extract_fallback_tool_call(content, {"read_file"})
    assert result is not None
    assert result["args"] == {"relative_path": "x.py"}


def test_fallback_rejects_unknown_tool_name():
    content = '{"name": "not_a_real_tool", "arguments": {}}'
    assert _extract_fallback_tool_call(content, {"read_file"}) is None


def test_fallback_rejects_plain_prose():
    assert _extract_fallback_tool_call("Sure, I can help with that!", {"read_file"}) is None


def test_fallback_rejects_malformed_json():
    assert _extract_fallback_tool_call('{"name": "read_file", oops}', {"read_file"}) is None


def test_fallback_rejects_json_without_name_or_arguments():
    assert _extract_fallback_tool_call('{"foo": "bar"}', {"read_file"}) is None


def test_is_capacity_error_still_works():
    assert is_capacity_error(Exception("429 rate limit exceeded")) is True
    assert is_capacity_error(Exception("invalid API key")) is False
