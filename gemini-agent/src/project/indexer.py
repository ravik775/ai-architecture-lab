"""Filesystem indexing: directory trees, shallow listings, and simple text search.

Everything in this module is pure filesystem access (no LLM calls) except
`analyze_project`, which is opt-in and used only by the sidebar's "Analyze
Project" button.
"""

from __future__ import annotations

import os
from pathlib import Path

import pathspec

from src.config import DEFAULT_IGNORE_DIRS, MAX_LIST_ENTRIES, MAX_SEARCH_RESULTS
from src.project.safety import read_file_safe, resolve_within_root

MANIFEST_FILES = (
    "README.md",
    "README.rst",
    "README.txt",
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
)


def _load_gitignore_spec(root: Path) -> pathspec.PathSpec | None:
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        return None
    lines = gitignore.read_text(encoding="utf-8", errors="ignore").splitlines()
    return pathspec.PathSpec.from_lines("gitwildmatch", lines)


def _is_default_ignored(rel_parts: tuple[str, ...]) -> bool:
    return any(part in DEFAULT_IGNORE_DIRS for part in rel_parts)


def iter_project_files(root: Path):
    """Yield paths (relative to root) for all non-ignored files."""
    spec = _load_gitignore_spec(root)

    for dirpath, dirnames, filenames in os.walk(root):
        dirpath_p = Path(dirpath)
        rel_dir = dirpath_p.relative_to(root)

        dirnames[:] = [
            d
            for d in dirnames
            if not _is_default_ignored((*rel_dir.parts, d))
            and not (spec and spec.match_file(str((rel_dir / d)) + "/"))
        ]

        for name in filenames:
            rel_path = rel_dir / name if str(rel_dir) != "." else Path(name)
            if _is_default_ignored(rel_path.parts):
                continue
            if spec and spec.match_file(str(rel_path)):
                continue
            yield rel_path


def build_tree(root: Path, max_depth: int = 3) -> str:
    """Render an indented directory tree, pruned at max_depth."""
    root = root.resolve()
    lines = [f"{root.name}/"]

    all_files = sorted(iter_project_files(root), key=lambda p: str(p))
    tree: dict = {}
    for rel_path in all_files:
        node = tree
        for part in rel_path.parts[:-1]:
            node = node.setdefault(part, {})
        node.setdefault("__files__", []).append(rel_path.name)

    def render(node: dict, prefix: str, depth: int):
        if depth > max_depth:
            if node:
                lines.append(f"{prefix}...")
            return
        dirs = sorted(k for k in node if k != "__files__")
        files = sorted(node.get("__files__", []))
        for d in dirs:
            lines.append(f"{prefix}{d}/")
            render(node[d], prefix + "  ", depth + 1)
        for f in files:
            lines.append(f"{prefix}{f}")

    render(tree, "  ", 1)
    return "\n".join(lines)


def list_dir_entries(root: Path, relative_path: str = ".") -> str:
    """Shallow (non-recursive) listing of a directory, capped in size."""
    target = resolve_within_root(root, relative_path)
    if not target.is_dir():
        return f"Error: '{relative_path}' is not a directory."

    spec = _load_gitignore_spec(root)
    rel_target = target.relative_to(root)

    entries = []
    for entry in sorted(target.iterdir(), key=lambda p: p.name):
        rel_entry = rel_target / entry.name if str(rel_target) != "." else Path(entry.name)
        if _is_default_ignored(rel_entry.parts):
            continue
        if spec and spec.match_file(str(rel_entry) + ("/" if entry.is_dir() else "")):
            continue
        entries.append(f"{entry.name}/" if entry.is_dir() else entry.name)

    truncated = len(entries) > MAX_LIST_ENTRIES
    entries = entries[:MAX_LIST_ENTRIES]
    out = "\n".join(entries) if entries else "(empty directory)"
    if truncated:
        out += f"\n... [truncated, more than {MAX_LIST_ENTRIES} entries]"
    return out


def search_text(root: Path, query: str, max_results: int = MAX_SEARCH_RESULTS) -> str:
    """Naive case-insensitive text search across all non-ignored project files."""
    if not query.strip():
        return "Error: search query must not be empty."

    query_lower = query.lower()
    matches: list[str] = []

    for rel_path in iter_project_files(root):
        full_path = root / rel_path
        try:
            content = full_path.read_text(encoding="utf-8", errors="ignore")
        except (UnicodeDecodeError, OSError):
            continue

        for lineno, line in enumerate(content.splitlines(), start=1):
            if query_lower in line.lower():
                snippet = line.strip()[:200]
                matches.append(f"{rel_path.as_posix()}:{lineno}: {snippet}")
                if len(matches) >= max_results:
                    return "\n".join(matches) + f"\n... [stopped at {max_results} matches]"

    return "\n".join(matches) if matches else f"No matches found for '{query}'."


def analyze_project(root: Path, llm) -> str:
    """Ask the LLM for a short summary of the project's stack and structure."""
    from langchain_core.messages import HumanMessage, SystemMessage

    tree = build_tree(root, max_depth=3)

    manifest_snippets = []
    for name in MANIFEST_FILES:
        candidate = root / name
        if candidate.is_file():
            try:
                content = read_file_safe(candidate, max_bytes=4000)
            except OSError:
                continue
            manifest_snippets.append(f"--- {name} ---\n{content}")

    manifest_text = "\n\n".join(manifest_snippets) if manifest_snippets else "(none found)"

    prompt = (
        "You are analyzing a software project's directory tree and key manifest "
        "files. Write a concise summary (max ~150 words) covering: the tech "
        "stack/languages, the overall structure, and likely entry points. "
        "Do not list every file.\n\n"
        f"Directory tree:\n{tree}\n\nManifest files:\n{manifest_text}"
    )

    response = llm.invoke(
        [
            SystemMessage(content="You are a precise, terse code analysis assistant."),
            HumanMessage(content=prompt),
        ]
    )
    return response.content
