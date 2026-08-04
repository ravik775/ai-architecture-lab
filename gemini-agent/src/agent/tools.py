"""LangChain tools bound to a specific project root and pending-change store.

Read-only tools (list_directory, get_project_tree, read_file, search_code)
touch the filesystem directly. The only tools that create effects,
propose_file_change / propose_file_delete, never write to disk themselves —
they stage an entry in the PendingChangeStore for the user to review.
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from src.changes.store import PendingChangeStore
from src.project.indexer import build_tree, list_dir_entries, search_text
from src.project.safety import PathSecurityError, read_file_safe, resolve_within_root


def build_tools(project_root: Path, change_store: PendingChangeStore) -> list:
    @tool
    def list_directory(relative_path: str = ".") -> str:
        """List files and subdirectories directly inside a project directory
        (non-recursive). Use '.' for the project root."""
        try:
            return list_dir_entries(project_root, relative_path)
        except PathSecurityError as exc:
            return f"Error: {exc}"

    @tool
    def get_project_tree(max_depth: int = 3) -> str:
        """Return an indented tree view of the whole project, pruned at
        max_depth directory levels."""
        return build_tree(project_root, max_depth=max_depth)

    @tool
    def read_file(relative_path: str) -> str:
        """Read the text content of a file, given a path relative to the
        project root."""
        try:
            target = resolve_within_root(project_root, relative_path)
        except PathSecurityError as exc:
            return f"Error: {exc}"
        if not target.exists():
            return f"Error: '{relative_path}' does not exist."
        if not target.is_file():
            return f"Error: '{relative_path}' is not a file."
        try:
            return read_file_safe(target)
        except (UnicodeDecodeError, OSError) as exc:
            return f"Error: could not read '{relative_path}': {exc}"

    @tool
    def search_code(query: str) -> str:
        """Case-insensitive text search across all project files. Returns
        matching 'path:line: snippet' entries."""
        try:
            return search_text(project_root, query)
        except PathSecurityError as exc:
            return f"Error: {exc}"

    @tool
    def propose_file_change(relative_path: str, new_content: str, description: str) -> str:
        """Stage a new file or a full-content replacement of an existing file
        for user approval. `new_content` must be the COMPLETE new file
        content, not a diff/patch. Nothing is written to disk until the user
        approves and applies the change."""
        try:
            return change_store.stage_change(project_root, relative_path, new_content, description)
        except PathSecurityError as exc:
            return f"Error: {exc}"

    @tool
    def propose_file_delete(relative_path: str, description: str) -> str:
        """Stage deletion of a file for user approval. Nothing is deleted
        until the user approves and applies the change."""
        try:
            return change_store.stage_delete(project_root, relative_path, description)
        except PathSecurityError as exc:
            return f"Error: {exc}"

    return [
        list_directory,
        get_project_tree,
        read_file,
        search_code,
        propose_file_change,
        propose_file_delete,
    ]
