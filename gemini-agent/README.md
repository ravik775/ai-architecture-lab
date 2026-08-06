# Local Coding Agent

A lightweight, laptop-local "Cowork"-style assistant. Point it at a project folder, chat with
it about the code, and let it propose edits or new files — nothing is written to disk until you
review and approve each change as a diff.

Built with:
- **LiteLLM** — talks to Gemini, OpenRouter, or any other litellm-supported model
- **LangChain** (`langchain-core`) — message types, tool definitions, `BaseChatModel`
- **LangGraph** — the ReAct-style tool-calling agent loop (`create_react_agent`)
- **Streamlit** — local web UI

## Setup

Uses [uv](https://docs.astral.sh/uv/) for dependency management, with the virtual environment
named `gemini` (instead of uv's default `.venv`):

```bash
$env:UV_PROJECT_ENVIRONMENT = "gemini"   # PowerShell; use `export` on macOS/Linux
uv sync
copy .env.example .env                   # then paste your key into .env
```

This creates `gemini/` (the venv) and `uv.lock` (the resolved dependency lockfile) from
`pyproject.toml`. Re-run `uv sync` after pulling changes that touch `pyproject.toml`.

Pick a provider and put its key in `.env` (see `.env.example`) — you only need the one you plan
to use:
- Gemini: `GEMINI_API_KEY=...` from https://aistudio.google.com/apikey (`GOOGLE_API_KEY` also works)
- OpenRouter: `OPENROUTER_API_KEY=...` from https://openrouter.ai/keys

You can instead paste a key into the sidebar at runtime — it's kept in-memory only for that
session and never written to disk.

### Adding providers/models

Providers, their models, and which env var(s) each one's key comes from are all defined in
[`config/models.yaml`](config/models.yaml) — not hardcoded in Python. To add a model, add a line
under the relevant provider's `models:` list; to add a whole new litellm-supported provider, add
a new top-level entry with `api_key_env_vars`, `key_url`, and `models`. No code changes needed;
just restart the app.

## Run

```bash
gemini\Scripts\streamlit run app.py    # Windows
gemini/bin/streamlit run app.py        # macOS/Linux
```

This opens a local browser tab (default `http://localhost:8501`).

## Using it

1. **Sidebar → Project**: enter or browse to a project folder.
2. **Sidebar → Model**: pick a provider, then a model for that provider (or type a custom
   litellm model string to override both).
3. **Sidebar → Analysis**: optionally click "Analyze project" for a quick stack/structure summary
   the agent will use as context.
4. **Chat**: ask questions, request explanations, or ask for code changes/new files.
5. **Pending changes** (right panel): every proposed edit shows up here as a unified diff. Review
   each file, Approve/Reject individually (or Approve all), then click **Apply approved** to
   actually write the changes to disk.

The agent can only read/write inside the selected project folder — every tool call is checked
against the resolved project root, and file writes are staged in memory until you explicitly
apply them.

## Manual verification checklist

Automated tests (`pytest tests/`) cover the path-safety guard and the change-staging logic, but
exercising the full agent loop needs a real API key:

1. Set `GEMINI_API_KEY`, run the app, select a small test project folder.
2. Ask a read-only question ("what does this project do?") — confirm a sensible answer with no
   pending changes appearing.
3. Ask for a small change ("add a `.gitignore` entry for `*.log`" or similar) — confirm a diff
   appears in the pending-changes panel with a sensible description.
4. Reject a change — confirm it disappears and the file on disk is untouched.
5. Approve a change and click **Apply approved** — confirm the file on disk now matches the diff.
6. Try asking it to read/write a path outside the project root (e.g. `../../etc/passwd`) —
   confirm the tool returns a path-security error instead of touching anything.

## Troubleshooting

- **`uv: command not found`** — install it from https://docs.astral.sh/uv/getting-started/installation/,
  or use plain `pip install -e .` into a normal `venv` instead (the app has no uv-specific code).
- **Sidebar shows "No API key set" even after editing `.env`** — the app only reads `.env` at
  process start; restart `streamlit run app.py` after changing it.
- **"Analysis failed" / chat errors mentioning 401, 403, or "API key not valid"** — the key is
  missing, wrong, or doesn't have Gemini API access enabled; regenerate it at
  https://aistudio.google.com/apikey.
- **Chat errors mentioning 429 / rate limit / quota** — you've hit the free-tier rate limit for
  the selected model; wait a bit or switch models in the sidebar.
- **"No folder dialog available here"** — the `Browse…` button needs a desktop session (tkinter +
  a display); over SSH or in a headless/container environment, just type the path manually.
- **Port 8501 already in use** — another Streamlit app is running; stop it, or run
  `streamlit run app.py --server.port 8502`.

## Project layout

```
app.py                  Streamlit entrypoint
config/models.yaml       Provider/model catalog (edit this to add providers or models)
src/config.py            Loads config/models.yaml, ignore dirs, size limits, .env loading
src/agent/llm.py          BaseChatModel wrapping litellm.completion (tool-calling support)
src/agent/tools.py         Project-bound LangChain tools (read/list/search/propose_*)
src/agent/prompts.py        System prompt
src/agent/graph.py           LangGraph create_react_agent wiring
src/project/indexer.py    Directory tree, shallow listing, text search, AI project summary
src/project/safety.py      Path-escape guard, size-capped file reads
src/changes/store.py      In-memory staged-change store (diff/approve/reject/apply)
src/ui/*                  Streamlit sidebar, chat panel, diff/approval panel
tests/                    pytest coverage for safety + store
```
