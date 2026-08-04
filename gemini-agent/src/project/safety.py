"""Guards that keep the agent's file tools confined to the selected project root."""

from __future__ import annotations

from pathlib import Path

from src.config import MAX_FILE_BYTES


class PathSecurityError(Exception):
    """Raised when a relative path would escape the project root."""


def resolve_within_root(root: Path, relative_path: str) -> Path:
    """Resolve `relative_path` against `root`, refusing to leave it.

    Rejects absolute paths and any traversal (`..`) that would escape the
    project root, even after symlink/`.`/`..` resolution.
    """
    root = root.resolve()
    candidate = (root / relative_path).resolve()

    if not (candidate == root or candidate.is_relative_to(root)):
        raise PathSecurityError(
            f"'{relative_path}' resolves outside the project root ({root})."
        )
    return candidate


def read_file_safe(path: Path, max_bytes: int = MAX_FILE_BYTES) -> str:
    """Read a text file, truncating with a notice if it exceeds `max_bytes`."""
    data = path.read_bytes()
    truncated = len(data) > max_bytes
    if truncated:
        data = data[:max_bytes]

    text = data.decode("utf-8", errors="replace")
    if truncated:
        text += f"\n\n... [truncated, file exceeds {max_bytes} bytes]"
    return text
