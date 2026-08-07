"""Pre-execution planning: break a large/complex request into self-contained phases.

This is a proactive complement to compaction.py's reactive history-trimming:
instead of only cleaning up context after it has already grown too large, a
big incoming request is split up front into a small number of bounded,
self-contained phase instructions, so no single agent turn ever needs the
whole original request in context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage

from src.agent.llm import LiteLLMChatModel

# Below this, a request is already small enough for one agent turn - skip the
# planner round-trip entirely rather than pay for it on "add a .gitignore".
MIN_CHARS_TO_PLAN = 800

_PHASE_HEADER_RE = re.compile(r"^###\s*Phase\s+\d+\s*:\s*(.+)$", re.MULTILINE)

_SYSTEM_PROMPT = """You are a planning assistant. Break the user's request into a small \
number of self-contained phases that can each be completed independently, one at a time, \
without needing to re-read the original request.

Rules:
- Each phase's instructions must be COMPLETE and SELF-CONTAINED - include every detail \
(file names, requirements, field names, etc.) needed to complete just that phase, since \
the original request will not be shown again when that phase runs.
- Order phases so each one only depends on phases before it.
- Use 2-8 phases. If the request is already small/simple, output exactly one phase \
containing the whole request unchanged.
- Output ONLY phases in this exact format, nothing else - no preamble, no explanation:

### Phase 1: <short title>
<full self-contained instructions for this phase>

### Phase 2: <short title>
<full self-contained instructions for this phase>

(and so on)

Example input: "Build a CLI todo app: add/list/complete/delete tasks, store in a JSON \
file, add tests."

Example output:
### Phase 1: Project setup and data model
Create a Python CLI todo app project. Set up pyproject.toml and a Task data model \
(id, text, done: bool) stored as a list of dicts in tasks.json in the project root. \
Add load_tasks()/save_tasks() helper functions.

### Phase 2: Add and list commands
Add a CLI command `add <text>` that appends a new Task to tasks.json with a new \
integer id, and a command `list` that prints all tasks with their id, done status, \
and text.

### Phase 3: Complete and delete commands
Add a CLI command `complete <id>` that marks the matching task's done field True, \
and a command `delete <id>` that removes the matching task, both saving back to \
tasks.json.

### Phase 4: Tests
Add pytest tests covering add, list, complete, and delete against a temporary \
tasks.json, verifying the JSON file contents after each operation."""


@dataclass
class Phase:
    title: str
    instructions: str


def _parse_phases(text: str) -> list[Phase]:
    headers = list(_PHASE_HEADER_RE.finditer(text))
    if not headers:
        return []
    phases = []
    for i, m in enumerate(headers):
        title = m.group(1).strip()
        start = m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        instructions = text[start:end].strip()
        if instructions:
            phases.append(Phase(title=title, instructions=instructions))
    return phases


def plan_phases(request: str, model: str, api_key: str | None) -> list[Phase]:
    """Split `request` into phases, or return it unchanged as a single phase
    if it's already small or the planner fails/produces nothing parseable.
    Callers should treat a single-phase result as "no split happened" and
    just run the request directly - planning failure never blocks sending."""
    if len(request) < MIN_CHARS_TO_PLAN:
        return [Phase(title="Full request", instructions=request)]

    llm = LiteLLMChatModel(model=model, api_key=api_key)
    try:
        response = llm.invoke(
            [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=request)]
        )
        phases = _parse_phases(str(response.content))
    except Exception:
        phases = []

    return phases or [Phase(title="Full request", instructions=request)]
