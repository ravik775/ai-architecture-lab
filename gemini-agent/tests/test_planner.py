from src.agent.planner import Phase, _parse_phases, plan_phases


def test_parse_phases_splits_on_headers():
    text = """### Phase 1: Setup
Create pyproject.toml and the base package layout.

### Phase 2: Core logic
Implement the add/list commands against tasks.json.

### Phase 3: Tests
Add pytest coverage for add and list."""
    phases = _parse_phases(text)
    assert [p.title for p in phases] == ["Setup", "Core logic", "Tests"]
    assert "pyproject.toml" in phases[0].instructions
    assert "pytest" in phases[2].instructions


def test_parse_phases_returns_empty_for_unstructured_text():
    assert _parse_phases("Sure, here's a plan for your app...") == []


def test_parse_phases_ignores_header_with_no_body():
    text = "### Phase 1: Empty\n\n### Phase 2: Has content\nDo the thing."
    phases = _parse_phases(text)
    assert len(phases) == 1
    assert phases[0].title == "Has content"


def test_plan_phases_skips_planner_for_short_requests():
    # Well under MIN_CHARS_TO_PLAN - must return the request untouched as a
    # single phase without ever invoking the model (no model/key needed).
    phases = plan_phases("add a .gitignore", model="unused/should-not-be-called", api_key=None)
    assert phases == [Phase(title="Full request", instructions="add a .gitignore")]
