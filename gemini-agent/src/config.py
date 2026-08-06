"""Central configuration for the local Gemini coding agent."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env from the project root (if present) before anything reads env vars.
load_dotenv(_PROJECT_ROOT / ".env")

# --- Models -----------------------------------------------------------------
#
# Providers, their litellm-prefixed models, and where each one's API key
# comes from are defined in config/models.yaml, not hardcoded here — add a
# provider or model there and it shows up in the app with no code changes.

MODELS_CONFIG_PATH = _PROJECT_ROOT / "config" / "models.yaml"


def _load_config(path: Path) -> tuple[dict[str, dict], str, dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    providers = {
        name: {
            "models": cfg["models"],
            "api_key_env_vars": tuple(cfg["api_key_env_vars"]),
            "key_url": cfg.get("key_url", ""),
        }
        for name, cfg in data["providers"].items()
    }

    enhancer_cfg = data.get("prompt_enhancer") or {}
    prompt_enhancer = {
        "model": enhancer_cfg.get("model"),
        "api_key_env_vars": tuple(enhancer_cfg.get("api_key_env_vars", ())),
    }

    return providers, data["default_provider"], prompt_enhancer


PROVIDERS, DEFAULT_PROVIDER, PROMPT_ENHANCER = _load_config(MODELS_CONFIG_PATH)


def get_api_key(env_vars: tuple[str, ...]) -> str | None:
    for var in env_vars:
        value = os.environ.get(var)
        if value:
            return value
    return None


# --- Project indexing ---------------------------------------------------------

DEFAULT_IGNORE_DIRS = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "env",
    "__pycache__",
    "dist",
    "build",
    ".idea",
    ".vscode",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "egg-info",
    ".next",
    ".turbo",
}

# Files larger than this are truncated when read by the agent.
MAX_FILE_BYTES = 200_000

# Cap on number of matches returned by the search tool.
MAX_SEARCH_RESULTS = 50

# Cap on number of entries returned by list_directory.
MAX_LIST_ENTRIES = 200

# Safety cap on agent tool-calling turns per user message.
AGENT_RECURSION_LIMIT = 25

# Max models a user can chain as fallbacks in the sidebar - if one is
# rate-limited/out of credits, the next is tried automatically.
MAX_MODEL_CHAIN = 4
