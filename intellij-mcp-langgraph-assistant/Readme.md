# text-polisher — an MCP Server reference example

`text-polisher` is a deliberately small MCP server. Its job (polishing text)
isn't the point — the point is that it exposes all three **server-side
primitives** defined by the Model Context Protocol (MCP) so you can see how
each one behaves, using one consistent example throughout: **polishing a
piece of text**.

## What MCP is, briefly

MCP is a client-server protocol that lets an AI application (the "host" —
e.g. Claude Desktop, an IDE, or a custom agent) connect to external servers
that expose context and capabilities in a standardized way. A server can
expose three things:

| Primitive | Who decides when it's used | What it's for |
|---|---|---|
| **Resource** | The host / user | Read-only context data |
| **Prompt** | The user | A reusable, user-selected interaction template |
| **Tool** | The model | An executable action with typed inputs/outputs |

This server implements one of each, all built around the same task.

---

## 1. Resources — read-only context

Resources are data the host can pull into context. The model doesn't "call"
a resource the way it calls a tool — the application decides when to fetch
it and hand it to the model as background information.

- **`resource://style-guide`** — the company's writing standards (active
  voice, sentence length, tone, etc.)
- **`resource://writing-rules`** — general mechanical writing rules
  (capitalization, one idea per sentence, etc.)

**Use case:** before asking the model to polish anything, a host can fetch
both resources and include them as context, so every edit the model makes
is grounded in an actual, inspectable style guide instead of the model's
own opinion of "good writing."

---

## 2. Prompts — reusable, user-selected workflows

A prompt is a template the *user* explicitly picks (e.g. as a slash command
in a client), not something the model invokes on its own. Prompts are how
you package a repeatable workflow — "read this context, then do this
action, in this way" — so users don't have to reconstruct it by hand every
time.

- **`polish_for_channel(raw_text, channel)`** — walks through polishing text
  for a specific destination (`email`, `chat`, or `doc`). It tells the host
  to read the two resources above for context, then invoke the
  `polish_text` tool, with channel-specific guidance (e.g. a doc should be
  formal with no contractions; a chat message should be brief).

**Use case:** a user picks the `polish_for_channel` prompt in their MCP
client, chooses `channel=doc`, and gets a consistent, repeatable workflow —
read style guide → read writing rules → polish — instead of typing that
sequence out every time.

**Sample prompt text you can try in a client that supports MCP prompts:**

```
/polish_for_channel raw_text="pls send the report asap thx" channel="email"
```

---

## 3. Tools — model-controlled executable actions

Tools are functions the model decides to call, with a typed input schema
and a typed, structured return value — this is what lets a tool's output be
consumed programmatically by other steps in a pipeline, not just read as
chat text.

- **`polish_text(raw_text: str) -> PolishedText`** — sends the text through
  an LLM chain (via `ChatLiteLLM`, model configurable through `MODEL_NAME`)
  bound to a structured output schema:

  ```python
  class PolishedText(BaseModel):
      text: str            # the rewritten text
      changes_made: list[str]  # bullet list of what was changed
  ```

  The chain uses `.with_structured_output(PolishedText)` rather than asking
  the model to return free-form JSON and parsing it by hand — this removes
  an entire class of failures (stray markdown fences, truncated output,
  extra prose around the JSON) that manual parsing is exposed to.

**Use case:** an agent building a "send professional email" workflow calls
`polish_text` directly on a draft, and can programmatically check
`changes_made` to log what was edited, without asking the model to
re-explain itself in prose.

**Sample prompt text you can try directly:**

```
Polish the following paragraph using #polish_text

Hey just wanted to check if you got my email last week let me know thanks
```

---

## Transports

The server supports both MCP transports, controlled by `MCP_TRANSPORT`:

- **`stdio`** — for local development, e.g. from an editor. See
  `app/vscode/mcp.json` for the local launch config (`uv run app/main.py`).
- **`streamable-http`** — for running the server as a persistent process
  reachable over the network (used by the Docker deployment below).

> **Note:** the HTTP transport, as configured here, has no authentication
> layer. That's acceptable for local/demo use on a trusted network, but if
> you expose this server beyond localhost, put a reverse proxy with auth in
> front of it — otherwise anything that can reach the port can invoke
> `polish_text` and consume your model budget.

## Running it

**Locally (stdio), via VS Code / any MCP-aware editor:**
The config in `app/vscode/mcp.json` will launch the server with `uv run
app/main.py` and connect over stdio automatically.

**As a container (streamable-http):**

```bash
docker compose up --build
```

This starts the server on `http://localhost:8000/mcp`, matching the
`text-polisher` entry in `app/vscode/mcp.json`.

Set your model credentials in `app/.env` (not committed — see
`.dockerignore`), e.g.:

```
OPENAI_API_KEY=sk-...
MODEL_NAME=gpt-4o-mini
```

## What's intentionally *not* here

To keep this a clean, minimal reference, this server does not implement:

- **Sampling** (a server asking the *client's* model for a completion) or
  **Elicitation** (a server asking the user for missing input) — these are
  client-exposed primitives, out of scope for a single-tool demo, but worth
  exploring as a follow-up if you want to see the full primitive set MCP
  defines.
- Additional tools like `summarize_text` or `rewrite_email` — an earlier
  draft of this README sketched these in an architecture diagram, but they
  were never implemented. They've been removed from the docs here rather
  than left as a promise the code doesn't keep. They'd be natural, low-risk
  additions if you want to extend the tool set later.