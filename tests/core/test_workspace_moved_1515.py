"""#1515 — a workspace's repo_path is where `.codeframe/` is now, not where it was made.

The stored path went stale on a move (every proof check "not collected") and,
worse, on a copy: the copy's proof run tested the original tree.
"""

import shutil

import pytest

from codeframe.core.workspace import create_or_load_workspace, get_workspace

pytestmark = pytest.mark.v2


def test_a_moved_repo_points_at_its_new_path(tmp_path):
    original = tmp_path / "a"
    original.mkdir()
    create_or_load_workspace(original)
    moved = tmp_path / "b"
    original.rename(moved)

    assert get_workspace(moved).repo_path == moved.resolve()


def test_a_copied_repo_points_at_the_copy_not_the_original(tmp_path):
    original = tmp_path / "a"
    original.mkdir()
    create_or_load_workspace(original)
    copy = tmp_path / "b"
    shutil.copytree(original, copy)

    assert get_workspace(copy).repo_path == copy.resolve()
    assert create_or_load_workspace(copy).repo_path == copy.resolve()
