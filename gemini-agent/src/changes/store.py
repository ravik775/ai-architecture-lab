"""In-memory staging area for proposed file changes, pending user approval.

Nothing here ever touches disk except `apply_approved`, which is only called
from the UI after the user has explicitly approved each change.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from src.project.safety import resolve_within_root

Action = Literal["create", "modify", "delete"]
Status = Literal["pending", "approved", "rejected", "applied"]


@dataclass
class PendingChange:
    path: str  # posix-style, relative to project root; also the store's dict key
    action: Action
    old_content: str | None
    new_content: str | None
    description: str
    status: Status = "pending"

    def diff(self) -> str:
        old_lines = (self.old_content or "").splitlines(keepends=True)
        new_lines = (self.new_content or "").splitlines(keepends=True)
        diff_lines = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile="/dev/null" if self.old_content is None else f"a/{self.path}",
            tofile="/dev/null" if self.new_content is None else f"b/{self.path}",
        )
        text = "".join(diff_lines)
        return text or "(no textual changes)"


@dataclass
class PendingChangeStore:
    changes: dict[str, PendingChange] = field(default_factory=dict)

    def stage_change(
        self, root: Path, relative_path: str, new_content: str, description: str
    ) -> str:
        target = resolve_within_root(root, relative_path)
        rel_key = target.relative_to(root.resolve()).as_posix()

        if target.exists():
            old_content = target.read_text(encoding="utf-8", errors="replace")
            action: Action = "modify"
        else:
            old_content = None
            action = "create"

        self.changes[rel_key] = PendingChange(
            path=rel_key,
            action=action,
            old_content=old_content,
            new_content=new_content,
            description=description,
        )
        return f"Staged {action} for '{rel_key}' — awaiting user approval."

    def stage_delete(self, root: Path, relative_path: str, description: str) -> str:
        target = resolve_within_root(root, relative_path)
        rel_key = target.relative_to(root.resolve()).as_posix()

        if not target.exists():
            return f"Error: '{relative_path}' does not exist, nothing to delete."

        old_content = (
            target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
        )
        self.changes[rel_key] = PendingChange(
            path=rel_key,
            action="delete",
            old_content=old_content,
            new_content=None,
            description=description,
        )
        return f"Staged delete for '{rel_key}' — awaiting user approval."

    def approve(self, path: str) -> None:
        if path in self.changes:
            self.changes[path].status = "approved"

    def reject(self, path: str) -> None:
        if path in self.changes:
            self.changes[path].status = "rejected"

    def approve_all(self) -> None:
        for change in self.changes.values():
            if change.status == "pending":
                change.status = "approved"

    def clear_resolved(self) -> None:
        self.changes = {
            k: v for k, v in self.changes.items() if v.status not in ("rejected", "applied")
        }

    def pending(self) -> list[PendingChange]:
        return [c for c in self.changes.values() if c.status == "pending"]

    def approved(self) -> list[PendingChange]:
        return [c for c in self.changes.values() if c.status == "approved"]

    def apply_approved(self, root: Path) -> list[str]:
        """Write every approved change to disk and mark it applied."""
        applied = []
        for change in self.approved():
            target = root.resolve() / change.path
            if change.action == "delete":
                if target.exists():
                    target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(change.new_content or "", encoding="utf-8")
            change.status = "applied"
            applied.append(change.path)
        return applied
