"""Direct unit tests for codeframe.core.artifacts.

Exercises patch export, commit creation, status parsing, and patch listing
against a real git repo + real Workspace (so the emitted events are persisted
to the workspace DB). Error paths that depend on git being absent are covered
by patching ``shutil.which``. The pure parse helpers are tested in isolation.

Issue #654 (P6.8.1): test coverage hardening for untested core modules.
"""

import subprocess
from pathlib import Path

import pytest

from codeframe.core import artifacts
from codeframe.core import events
from codeframe.core.artifacts import (
    PatchInfo,
    CommitInfo,
    export_patch,
    create_commit,
    get_status,
    list_patches,
    _get_diff_stats,
    _parse_patch_content_stats,
)
from codeframe.core.workspace import Workspace, create_or_load_workspace


pytestmark = pytest.mark.v2


def _bare_workspace(repo_path: Path) -> Workspace:
    """A Workspace carrying only the path attributes artifacts.py reads.

    Intentionally bypasses __init__ (no DB/event setup) for tests that exercise
    pure-filesystem / error paths and never emit events. Sets every attribute
    artifacts.py touches (repo_path, state_dir); if Workspace grows a new
    required attribute that artifacts.py uses, those tests will fail loudly.
    """
    ws = Workspace.__new__(Workspace)
    ws.repo_path = repo_path
    ws.state_dir = repo_path / ".codeframe"
    return ws


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


def _init_repo(repo: Path, *, initial_commit: bool = True) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test User")
    if initial_commit:
        (repo / "hello.py").write_text("def hello():\n    return 'hello'\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "initial commit")


@pytest.fixture
def git_workspace(tmp_path, skip_if_no_git) -> Workspace:
    """A real Workspace backed by a git repo with one commit + an unstaged edit."""
    repo = tmp_path / "repo"
    _init_repo(repo, initial_commit=True)
    ws = create_or_load_workspace(repo)
    # Introduce an unstaged change so there's something to export.
    (repo / "hello.py").write_text(
        "def hello():\n    return 'hello world'\n\ndef bye():\n    return 'bye'\n"
    )
    return ws


# --- export_patch -----------------------------------------------------------


class TestExportPatch:
    def test_exports_unstaged_changes_to_autonamed_file(self, git_workspace):
        info = export_patch(git_workspace)

        assert isinstance(info, PatchInfo)
        assert info.path.exists()
        assert info.path.suffix == ".patch"
        # Auto-named under .codeframe/patches/
        assert info.path.parent.name == "patches"
        assert info.size_bytes > 0
        content = info.path.read_text()
        assert "def hello()" in content

    def test_export_emits_patch_exported_event(self, git_workspace):
        export_patch(git_workspace)
        recent = events.list_recent(git_workspace, limit=20)
        assert any(e.event_type == events.EventType.PATCH_EXPORTED for e in recent)

    def test_export_to_explicit_out_path(self, git_workspace, tmp_path):
        out = tmp_path / "custom.patch"
        info = export_patch(git_workspace, out_path=out)
        assert info.path == out
        assert out.exists()

    def test_export_staged_only(self, git_workspace):
        repo = git_workspace.repo_path
        _git(repo, "add", "hello.py")
        info = export_patch(git_workspace, staged_only=True)
        assert info.path.exists()
        assert info.files_changed >= 1

    def test_export_falls_back_to_plain_unstaged_without_initial_commit(
        self, tmp_path, skip_if_no_git
    ):
        """A repo with no commits: ``git diff HEAD`` errors/empties → plain diff."""
        repo = tmp_path / "fresh"
        _init_repo(repo, initial_commit=False)
        ws = create_or_load_workspace(repo)
        # Stage a file, then modify it again so there's a worktree-vs-index diff
        # that `git diff` (plain) reports but `git diff HEAD` cannot (no HEAD).
        (repo / "new.py").write_text("x = 1\n")
        _git(repo, "add", "new.py")
        (repo / "new.py").write_text("x = 1\ny = 2\nz = 3\n")

        info = export_patch(ws)
        assert info.path.exists()
        # Stats come from _parse_patch_content_stats on the fallback diff.
        assert info.insertions >= 1
        assert "new.py" in info.path.read_text()

    def test_export_no_changes_raises(self, tmp_path, skip_if_no_git):
        repo = tmp_path / "clean"
        _init_repo(repo, initial_commit=True)
        ws = create_or_load_workspace(repo)
        with pytest.raises(ValueError, match="No changes to export"):
            export_patch(ws)

    def test_export_not_a_git_repo_raises(self, tmp_path, skip_if_no_git):
        plain = tmp_path / "plain"
        plain.mkdir()
        ws = _bare_workspace(plain)
        with pytest.raises(ValueError, match="Not a git repository"):
            export_patch(ws)

    def test_export_git_not_found_raises(self, git_workspace, monkeypatch):
        monkeypatch.setattr(artifacts.shutil, "which", lambda _name: None)
        with pytest.raises(ValueError, match="git not found in PATH"):
            export_patch(git_workspace)


# --- create_commit ----------------------------------------------------------


class TestCreateCommit:
    def test_commit_with_add_all(self, git_workspace):
        info = create_commit(git_workspace, "feat: update hello", add_all=True)

        assert isinstance(info, CommitInfo)
        assert len(info.hash) == 7
        assert info.full_hash.startswith(info.hash)
        assert info.message == "feat: update hello"
        assert info.files_changed >= 1
        # hello.py is now committed: no longer a pending worktree/staged change.
        # (We don't assert a fully clean tree because emitting the COMMIT_CREATED
        # event writes to .codeframe/, which lives inside the repo.)
        status = get_status(git_workspace.repo_path)
        assert "hello.py" not in status["staged"]
        assert "hello.py" not in status["unstaged"]

    def test_commit_emits_commit_created_event(self, git_workspace):
        create_commit(git_workspace, "chore: commit", add_all=True)
        recent = events.list_recent(git_workspace, limit=20)
        assert any(e.event_type == events.EventType.COMMIT_CREATED for e in recent)

    def test_commit_pre_staged_changes(self, git_workspace):
        _git(git_workspace.repo_path, "add", "hello.py")
        info = create_commit(git_workspace, "feat: staged only", add_all=False)
        assert info.message == "feat: staged only"

    def test_commit_no_staged_changes_raises(self, git_workspace):
        # add_all=False and nothing staged → error.
        with pytest.raises(ValueError, match="No staged changes to commit"):
            create_commit(git_workspace, "nothing", add_all=False)

    def test_commit_git_not_found_raises(self, git_workspace, monkeypatch):
        monkeypatch.setattr(artifacts.shutil, "which", lambda _name: None)
        with pytest.raises(ValueError, match="git not found in PATH"):
            create_commit(git_workspace, "x", add_all=True)


# --- get_status -------------------------------------------------------------


class TestGetStatus:
    def test_clean_repo(self, tmp_path, skip_if_no_git):
        repo = tmp_path / "clean"
        _init_repo(repo, initial_commit=True)
        status = get_status(repo)
        assert status["clean"] is True
        assert status["staged"] == []
        assert status["unstaged"] == []
        assert status["untracked"] == []

    def test_unstaged_change(self, git_workspace):
        status = get_status(git_workspace.repo_path)
        assert status["clean"] is False
        assert "hello.py" in status["unstaged"]

    def test_staged_change(self, git_workspace):
        _git(git_workspace.repo_path, "add", "hello.py")
        status = get_status(git_workspace.repo_path)
        assert "hello.py" in status["staged"]

    def test_untracked_file(self, git_workspace):
        (git_workspace.repo_path / "brand_new.py").write_text("z = 3\n")
        status = get_status(git_workspace.repo_path)
        assert "brand_new.py" in status["untracked"]

    def test_staged_and_then_modified_again(self, git_workspace):
        """`MM` porcelain: a file staged then modified again appears in BOTH
        staged and unstaged — exercises the two-column parser directly."""
        repo = git_workspace.repo_path
        _git(repo, "add", "hello.py")
        # Modify again after staging → worktree differs from index too.
        (repo / "hello.py").write_text("def hello():\n    return 'third edit'\n")

        status = get_status(repo)
        assert "hello.py" in status["staged"]
        assert "hello.py" in status["unstaged"]


# --- list_patches -----------------------------------------------------------


class TestListPatches:
    def test_missing_patches_dir_returns_empty(self, tmp_path):
        ws = _bare_workspace(tmp_path)  # .codeframe/ does not exist
        assert list_patches(ws) == []

    def test_lists_patches_newest_first(self, tmp_path):
        ws = _bare_workspace(tmp_path)
        patches_dir = ws.state_dir / "patches"
        patches_dir.mkdir(parents=True)

        sample = (
            "diff --git a/a.py b/a.py\n"
            "--- a/a.py\n+++ b/a.py\n@@ -0,0 +1 @@\n+print('a')\n"
        )
        (patches_dir / "patch-20240101-000000.patch").write_text(sample)
        (patches_dir / "patch-20240102-000000.patch").write_text(sample)

        result = list_patches(ws)
        assert len(result) == 2
        # Sorted reverse by filename → newest (20240102) first.
        assert result[0].path.name == "patch-20240102-000000.patch"
        assert all(isinstance(p, PatchInfo) for p in result)
        assert result[0].files_changed == 1


# --- pure parse helpers -----------------------------------------------------


class TestParseHelpers:
    def test_parse_patch_content_stats_counts_files_and_lines(self):
        content = (
            "diff --git a/one.py b/one.py\n"
            "--- a/one.py\n+++ b/one.py\n"
            "@@ -1,2 +1,2 @@\n-old\n+new1\n+new2\n"
            "diff --git a/two.py b/two.py\n"
            "--- a/two.py\n+++ b/two.py\n"
            "@@ -1 +0,0 @@\n-gone\n"
        )
        stats = _parse_patch_content_stats(content)
        assert stats["files"] == 2
        # +new1, +new2 counted; +++ header lines excluded.
        assert stats["insertions"] == 2
        # -old and -gone counted; --- header lines excluded.
        assert stats["deletions"] == 2

    def test_parse_patch_content_stats_empty(self):
        assert _parse_patch_content_stats("") == {
            "files": 0,
            "insertions": 0,
            "deletions": 0,
        }

    def test_get_diff_stats_singular_and_plural(self, git_workspace):
        """Regex handles real ``git diff --stat`` summary lines."""
        repo = git_workspace.repo_path
        stats = _get_diff_stats(repo, staged_only=False)
        assert stats["files"] >= 1
        assert stats["insertions"] >= 1

    def test_get_diff_stats_no_changes(self, tmp_path, skip_if_no_git):
        repo = tmp_path / "clean"
        _init_repo(repo, initial_commit=True)
        assert _get_diff_stats(repo, staged_only=True) == {
            "files": 0,
            "insertions": 0,
            "deletions": 0,
        }
