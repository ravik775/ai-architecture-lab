"""Small on-disk persistence for state that must survive app restarts.

Streamlit's `session_state` is wiped every time the server process restarts
(which happens often during development, and on any crash/redeploy) — the
exhausted-models list needs to survive that, otherwise a model that just
failed shows up as available again on the very next restart.
"""

from __future__ import annotations

import json
from pathlib import Path

_STATE_DIR = Path(__file__).resolve().parent.parent / ".local_state"
EXHAUSTED_MODELS_FILE = _STATE_DIR / "exhausted_models.json"


def load_exhausted_models() -> dict[str, str]:
    if not EXHAUSTED_MODELS_FILE.exists():
        return {}
    try:
        return json.loads(EXHAUSTED_MODELS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_exhausted_models(exhausted: dict[str, str]) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    EXHAUSTED_MODELS_FILE.write_text(json.dumps(exhausted, indent=2), encoding="utf-8")
