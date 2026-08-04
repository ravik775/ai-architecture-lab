import pytest

from src.project.safety import PathSecurityError, read_file_safe, resolve_within_root


def test_resolve_within_root_allows_nested_path(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "file.py").write_text("x = 1")

    resolved = resolve_within_root(tmp_path, "sub/file.py")
    assert resolved == (tmp_path / "sub" / "file.py").resolve()


def test_resolve_within_root_allows_root_itself(tmp_path):
    resolved = resolve_within_root(tmp_path, ".")
    assert resolved == tmp_path.resolve()


def test_resolve_within_root_blocks_parent_traversal(tmp_path):
    with pytest.raises(PathSecurityError):
        resolve_within_root(tmp_path, "../outside.txt")


def test_resolve_within_root_blocks_deep_traversal(tmp_path):
    (tmp_path / "sub").mkdir()
    with pytest.raises(PathSecurityError):
        resolve_within_root(tmp_path, "sub/../../outside.txt")


def test_read_file_safe_truncates_large_files(tmp_path):
    big_file = tmp_path / "big.txt"
    big_file.write_text("a" * 1000)

    content = read_file_safe(big_file, max_bytes=100)
    assert content.startswith("a" * 100)
    assert "truncated" in content


def test_read_file_safe_returns_full_small_file(tmp_path):
    small_file = tmp_path / "small.txt"
    small_file.write_text("hello world")

    assert read_file_safe(small_file, max_bytes=100) == "hello world"
