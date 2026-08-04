import pytest

from src.changes.store import PendingChangeStore
from src.project.safety import PathSecurityError


def test_stage_change_marks_new_file_as_create(tmp_path):
    store = PendingChangeStore()
    msg = store.stage_change(tmp_path, "new.py", "print('hi')", "add greeting script")

    assert "create" in msg
    change = store.changes["new.py"]
    assert change.action == "create"
    assert change.old_content is None
    assert change.new_content == "print('hi')"
    assert change.status == "pending"


def test_stage_change_marks_existing_file_as_modify(tmp_path):
    existing = tmp_path / "existing.py"
    existing.write_text("old = 1")

    store = PendingChangeStore()
    store.stage_change(tmp_path, "existing.py", "new = 2", "update value")

    change = store.changes["existing.py"]
    assert change.action == "modify"
    assert change.old_content == "old = 1"
    assert "old = 1" in change.diff()
    assert "new = 2" in change.diff()


def test_stage_change_rejects_path_traversal(tmp_path):
    store = PendingChangeStore()
    with pytest.raises(PathSecurityError):
        store.stage_change(tmp_path, "../outside.py", "x = 1", "escape attempt")


def test_apply_approved_writes_file_and_marks_applied(tmp_path):
    store = PendingChangeStore()
    store.stage_change(tmp_path, "out.py", "value = 42", "create file")
    store.approve("out.py")

    applied = store.apply_approved(tmp_path)

    assert applied == ["out.py"]
    assert (tmp_path / "out.py").read_text() == "value = 42"
    assert store.changes["out.py"].status == "applied"


def test_apply_approved_ignores_pending_and_rejected(tmp_path):
    store = PendingChangeStore()
    store.stage_change(tmp_path, "pending.py", "a = 1", "desc")
    store.stage_change(tmp_path, "rejected.py", "b = 2", "desc")
    store.reject("rejected.py")

    applied = store.apply_approved(tmp_path)

    assert applied == []
    assert not (tmp_path / "pending.py").exists()
    assert not (tmp_path / "rejected.py").exists()


def test_stage_delete_and_apply_removes_file(tmp_path):
    target = tmp_path / "gone.py"
    target.write_text("bye = True")

    store = PendingChangeStore()
    store.stage_delete(tmp_path, "gone.py", "remove obsolete file")
    store.approve("gone.py")
    applied = store.apply_approved(tmp_path)

    assert applied == ["gone.py"]
    assert not target.exists()


def test_clear_resolved_keeps_only_pending_and_approved(tmp_path):
    store = PendingChangeStore()
    store.stage_change(tmp_path, "a.py", "1", "d")
    store.stage_change(tmp_path, "b.py", "2", "d")
    store.reject("a.py")

    store.clear_resolved()

    assert list(store.changes.keys()) == ["b.py"]
