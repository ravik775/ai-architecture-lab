"""
Deliberately simple in-memory conversation store.

Requirement #4 says to keep the LLM use case simple - the point of this
project is the observability plumbing, not a production memory backend.
Swap this module for Redis/Postgres-backed memory without touching the
graph or the observability code; that's the whole reason memory access
is isolated behind three functions.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import TypedDict

MAX_TURNS_PER_SESSION = 20  # cap to bound memory growth


class Message(TypedDict):
    role: str  # "user" | "assistant"
    content: str
    timestamp: float


class _InMemoryStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, deque[Message]] = defaultdict(lambda: deque(maxlen=MAX_TURNS_PER_SESSION))

    def get_history(self, session_id: str) -> list[Message]:
        with self._lock:
            return list(self._sessions[session_id])

    def append(self, session_id: str, role: str, content: str) -> None:
        with self._lock:
            self._sessions[session_id].append(Message(role=role, content=content, timestamp=time.time()))

    def session_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)


# Process-wide singleton - fine for a single-container demo service.
store = _InMemoryStore()
