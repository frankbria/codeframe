"""Tests for git review functions (diff stats, patch, commit message generation).

Tests the new functions added in core/git.py for the Review & Commit View (Issue #334).
"""

import pytest
from pathlib import Path

from codeframe.core.git import (
    get_diff_stats,
    get_patch,
    generate_commit_message,
    DiffStats,
    FileChange,
)
from codeframe.core.workspace import Workspace


@pytest.fixture
def git_workspace(tmp_path: Path) -> Workspace:
    """Create a workspace with a git repo that has uncommitted changes."""
    import subprocess

    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()

    # Init git repo
    subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_dir,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_dir,
        capture_output=True,
    )

    # Create initial file and commit
    (repo_dir / "hello.py").write_text("def hello():\n    return 'hello'\n")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial commit"],
        cwd=repo_dir,
        capture_output=True,
    )

    # Make a change (unstaged)
    (repo_dir / "hello.py").write_text(
        "def hello():\n    return 'hello world'\n\ndef greet():\n    return 'hi'\n"
    )

    ws = Workspace.__new__(Workspace)
    ws.repo_path = str(repo_dir)
    ws.state_dir = str(repo_dir / ".codeframe")
    return ws


@pytest.fixture
def git_workspace_new_file(git_workspace: Workspace) -> Workspace:
    """Workspace with an added new file (unstaged)."""
    repo_dir = Path(git_workspace.repo_path)
    (repo_dir / "new_module.py").write_text("# new module\ndef foo():\n    pass\n")
    return git_workspace


class TestGetDiffStats:
    def test_returns_diff_stats_with_changes(self, git_workspace):
        stats = get_diff_stats(git_workspace, staged=False)
        assert isinstance(stats, DiffStats)
        assert stats.files_changed >= 1
        assert stats.insertions >= 0
        assert stats.deletions >= 0
        assert len(stats.diff) > 0

    def test_returns_empty_for_clean_repo(self, tmp_path):
        """Clean repo should return zero stats."""
        import subprocess

        repo_dir = tmp_path / "clean_repo"
        repo_dir.mkdir()
        subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=repo_dir,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=repo_dir,
            capture_output=True,
        )
        (repo_dir / "f.txt").write_text("hi")
        subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, capture_output=True)

        ws = Workspace.__new__(Workspace)
        ws.repo_path = str(repo_dir)
        ws.state_dir = str(repo_dir / ".codeframe")

        stats = get_diff_stats(ws, staged=False)
        assert stats.files_changed == 0
        assert stats.insertions == 0
        assert stats.deletions == 0

    def test_changed_files_have_correct_structure(self, git_workspace):
        stats = get_diff_stats(git_workspace, staged=False)
        for fc in stats.changed_files:
            assert isinstance(fc, FileChange)
            assert fc.path
            assert fc.change_type in ("modified", "added", "deleted", "renamed")
            assert isinstance(fc.insertions, int)
            assert isinstance(fc.deletions, int)

    def test_diff_text_is_included(self, git_workspace):
        stats = get_diff_stats(git_workspace, staged=False)
        assert "hello" in stats.diff


class TestGetPatch:
    def test_returns_patch_content(self, git_workspace):
        patch = get_patch(git_workspace, staged=False)
        assert isinstance(patch, str)
        assert len(patch) > 0
        # Patch should contain diff markers
        assert "diff --git" in patch or "---" in patch

    def test_empty_for_clean_repo(self, tmp_path):
        import subprocess

        repo_dir = tmp_path / "clean_repo2"
        repo_dir.mkdir()
        subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo_dir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=repo_dir, capture_output=True)
        (repo_dir / "f.txt").write_text("hi")
        subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, capture_output=True)

        ws = Workspace.__new__(Workspace)
        ws.repo_path = str(repo_dir)
        ws.state_dir = str(repo_dir / ".codeframe")

        patch = get_patch(ws, staged=False)
        assert patch == ""


class TestGenerateCommitMessage:
    def test_generates_message_for_modified_file(self, git_workspace):
        msg = generate_commit_message(git_workspace, staged=False)
        assert isinstance(msg, str)
        assert len(msg) > 0
        assert ":" in msg  # conventional commit format

    def test_empty_for_no_changes(self, tmp_path):
        import subprocess

        repo_dir = tmp_path / "clean_repo3"
        repo_dir.mkdir()
        subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo_dir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=repo_dir, capture_output=True)
        (repo_dir / "f.txt").write_text("hi")
        subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, capture_output=True)

        ws = Workspace.__new__(Workspace)
        ws.repo_path = str(repo_dir)
        ws.state_dir = str(repo_dir / ".codeframe")

        msg = generate_commit_message(ws, staged=False)
        assert msg == ""

    def test_detects_test_files(self, tmp_path):
        """If only test files changed, prefix should be 'test'."""
        import subprocess

        repo_dir = tmp_path / "test_repo_tests"
        repo_dir.mkdir()
        subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo_dir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=repo_dir, capture_output=True)
        (repo_dir / "test_something.py").write_text("def test_a(): pass\n")
        subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, capture_output=True)

        # Modify test file
        (repo_dir / "test_something.py").write_text(
            "def test_a(): pass\ndef test_b(): pass\n"
        )

        ws = Workspace.__new__(Workspace)
        ws.repo_path = str(repo_dir)
        ws.state_dir = str(repo_dir / ".codeframe")

        msg = generate_commit_message(ws, staged=False)
        assert msg.startswith("test:")
