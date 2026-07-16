# 20-Minute MCP Hands-On: "Text Polisher" Server

**Goal:** Team members build a tiny MCP server (Python + LangChain + Pydantic) that exposes one tool — `polish_text` — which takes messy text and returns grammar-corrected, style-uniform text. They wire it into VS Code and call it live.

**Prereqs (send before session):**
- Python 3.10+
- `pip install mcp langchain langchain-anthropic pydantic`
- An `ANTHROPIC_API_KEY` set as an env var
- VS Code with GitHub Copilot Chat (or Continue) — needs MCP support enabled

---

## Segment 1 — Concepts Cheat Sheet (3 min)

Keep this to a whiteboard sketch, not a slide deck:

- **MCP** = a standard protocol so any LLM client (VS Code, Claude Desktop, etc.) can discover and call **tools**, read **resources**, or use **prompts** exposed by a **server** — without custom glue code per integration.
- **Architecture:** `Host (VS Code)` → `MCP Client` → `MCP Server (your Python process)`.
- **Primitives:**
  - *Tool* = a function the model can call (our case: `polish_text`)
  - *Resource* = read-only data the model can fetch (e.g. a style guide)
  - *Prompt* = a reusable prompt template exposed to the client
- **Transport:** `stdio` (local process, what we use today) vs `SSE/HTTP` (remote server).

One sentence to land: *"MCP is USB-C for tools — write the server once, any MCP-aware client can plug in."*

---

## Segment 2 — Build the Server (10 min)

### `text_polish_server.py`

```python
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate


class PolishedText(BaseModel):
    corrected_text: str = Field(
        description="Grammar-corrected, uniformly styled text"
    )
    changes_made: list[str] = Field(
        description="Short bullet list of edits made"
    )


llm = ChatOpenAI(
    model="gpt-5",
    temperature=0
)

structured_llm = llm.with_structured_output(PolishedText)

prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are an editor. Fix grammar and enforce a consistent, formal, third-person tone. Return the corrected text and a short list of changes."
    ),
    ("human", "{text}")
])

chain = prompt | structured_llm


mcp = FastMCP("text-polisher")


@mcp.tool()
def polish_text(text: str) -> dict:
    """Corrects grammar and enforces uniform tone/style in the given text."""
    result: PolishedText = chain.invoke({"text": text})
    return result.model_dump()


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

```python
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate

# ---- Pydantic schema: doubles as the LangChain structured-output contract ----
class PolishedText(BaseModel):
    corrected_text: str = Field(description="Grammar-corrected, uniformly styled text")
    changes_made: list[str] = Field(description="Short bullet list of edits made")

# ---- LangChain chain with structured output ----
llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)
structured_llm = llm.with_structured_output(PolishedText)

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an editor. Fix grammar and enforce a consistent, formal, "
               "third-person tone. Return the corrected text and a short list of changes."),
    ("human", "{text}")
])

chain = prompt | structured_llm

# ---- MCP server exposing it as a tool ----
mcp = FastMCP("text-polisher")

@mcp.tool()
def polish_text(text: str) -> dict:
    """Corrects grammar and enforces uniform tone/style in the given text."""
    result: PolishedText = chain.invoke({"text": text})
    return result.model_dump()

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

**Walk through while typing (don't just paste):**
1. `PolishedText` — this Pydantic model is the star of the exercise. It's used *both* as the LangChain `with_structured_output` contract *and* implicitly documents the tool's return shape.
2. `chain = prompt | structured_llm` — standard LangChain LCEL pipe; nothing MCP-specific yet.
3. `@mcp.tool()` — the only MCP-specific line. FastMCP inspects the function signature/docstring to auto-generate the tool's schema for the client.
4. `mcp.run(transport="stdio")` — server talks to its client over stdin/stdout, which is how VS Code will launch it.

**Quick local test (no VS Code needed):**
```bash
mcp dev text_polish_server.py
```
This opens the MCP Inspector in a browser — call `polish_text` directly with a sample sentence and show the JSON response before touching the editor.

---

## Segment 3 — Integrate with VS Code (4 min)

Create `.vscode/mcp.json` in the workspace:

```json
{
  "servers": {
    "text-polisher": {
      "command": "python",
      "args": ["text_polish_server.py"],
      "env": { "ANTHROPIC_API_KEY": "${env:ANTHROPIC_API_KEY}" }
    }
  }
}
```

Steps to demo:
1. Command Palette → **MCP: Add Server** (or just save the file above and reload).
2. Open Copilot Chat → the `text-polisher` server should appear under available tools/servers — enable it if prompted.
3. Confirm the `polish_text` tool is listed.

---

## Segment 4 — Live Exercise / Demo (3 min)

Give trainees this input and have them invoke the tool from Copilot Chat:

> "me and him goes to the store yesterday, and we was buying some things for the party which is happen tomorow"

Expected: a `corrected_text` in formal third person, plus a `changes_made` bullet list (grammar fixes, tense corrections, tone normalization).

Ask each trainee to run it once themselves — that's the "end to end" proof: VS Code → MCP client → your Python server → LangChain chain → Pydantic-validated JSON back to chat.

---

## Timing Recap

| Segment | Time |
|---|---|
| MCP concepts | 3 min |
| Build & test server | 10 min |
| VS Code integration | 4 min |
| Live exercise | 3 min |
| **Total** | **20 min** |

---

## Optional Stretch (post-session, not part of the 20 min)

- **LangSmith tracing:** set `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY=...` before running the server — every `chain.invoke` call now shows up as a trace in LangSmith, useful for showing observability without any code changes.
- Add a second tool, e.g. `summarize_text`, to show a server can expose more than one tool.
- Add a `resource` exposing a style-guide doc that the model can read before polishing.
