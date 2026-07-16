"""Worktree isolation end-to-end tests (issue #787).

Covers the single-run path re-enabling `--isolation worktree` with real
merge-back:
  - rebased_workspace keeps state on the main repo, code on the worktree (#715/#716)
  - TaskWorktree.auto_commit stages+commits worktree changes
  - runtime.execute_agent merges agent work back on success (file lands on base),
    turns a merge conflict into a blocker and preserves the branch, and preserves
    the branch on a failed run.

Uses a real git repo + real Workspace (no git mocking); the agent adapter is a
fake so behavior is deterministic without an LLM.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codeframe.core import tasks as tasks_mod
from codeframe.core import blockers as blockers_mod
from codeframe.core import runtime
from codeframe.core.adapters.agent_adapter import AgentResult
from codeframe.core.agent import AgentStatus
from codeframe.core.sandbox.context import rebased_workspace
from codeframe.core.workspace import create_or_load_workspace, Workspace

pytestmark = pytest.mark.v2


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


@pytest.fixture
def git_workspace(tmp_path: Path) -> Workspace:
    """A real git repo (branch 'main', one commit) with a CodeFRAME workspace."""
    subprocess.run(["git", "init", "-b", "main"], cwd=str(tmp_path), check=True, capture_output=True)
    _git(tmp_path, "config", "user.email", "test@test.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "README.md").write_text("seed")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "init")
    return create_or_load_workspace(tmp_path)


def _branch_exists(repo: Path, name: str) -> bool:
    out = subprocess.run(
        ["git", "-C", str(repo), "branch", "--list", name],
        capture_output=True, text=True,
    )
    return name in out.stdout


# ---------------------------------------------------------------------------
# rebased_workspace (#715 / #716 invariant)
# ---------------------------------------------------------------------------


class TestRebasedWorkspace:
    def test_repo_path_moves_state_stays(self, git_workspace: Workspace):
        worktree = git_workspace.repo_path / ".codeframe" / "worktrees" / "t1"
        rebased = rebased_workspace(git_workspace, worktree)
        # Code root follows the worktree...
        assert rebased.repo_path == worktree
        # ...but task/blocker/event state stays on the main-repo DB.
        assert rebased.state_dir == git_workspace.state_dir
        assert rebased.db_path == git_workspace.db_path

    def test_same_path_returns_same_workspace(self, git_workspace: Workspace):
        assert rebased_workspace(git_workspace, git_workspace.repo_path) is git_workspace


# ---------------------------------------------------------------------------
# auto_commit
# ---------------------------------------------------------------------------


class TestAutoCommit:
    def test_commits_dirty_worktree(self, git_workspace: Workspace):
        from codeframe.core.worktrees import TaskWorktree

        repo = git_workspace.repo_path
        wt = TaskWorktree()
        wtp = wt.create(repo, "t1", base_branch="main")
        (wtp / "new.txt").write_text("hi")

        assert wt.auto_commit(wtp, "t1") is True
        # HEAD of the branch now contains the file
        log = subprocess.run(
            ["git", "-C", str(wtp), "log", "-1", "--name-only", "--format="],
            capture_output=True, text=True,
        )
        assert "new.txt" in log.stdout

    def test_clean_worktree_is_noop(self, git_workspace: Workspace):
        from codeframe.core.worktrees import TaskWorktree

        wt = TaskWorktree()
        wtp = wt.create(git_workspace.repo_path, "t1", base_branch="main")
        assert wt.auto_commit(wtp, "t1") is False

    def test_commit_failure_raises_not_silent(self, git_workspace: Workspace):
        """Regression: a failed commit must raise, not report success — else the
        caller merges nothing and cleanup discards the agent's work (#714 class)."""
        from codeframe.core.worktrees import TaskWorktree

        repo = git_workspace.repo_path
        # A rejecting pre-commit hook lives in the shared .git/hooks (worktrees
        # share GIT_COMMON_DIR), so commits in the worktree fail.
        hooks = repo / ".git" / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        hook = hooks / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)

        wt = TaskWorktree()
        wtp = wt.create(repo, "t1", base_branch="main")
        (wtp / "work.txt").write_text("agent work")

        with pytest.raises(RuntimeError, match="git commit failed"):
            wt.auto_commit(wtp, "t1")


# ---------------------------------------------------------------------------
# runtime.execute_agent worktree wiring
# ---------------------------------------------------------------------------


class _FileWritingAdapter:
    """Fake external adapter that writes a file into the worktree it's given."""

    name = "claude-code"

    def __init__(self, filename: str, content: str):
        self._filename = filename
        self._content = content

    def run(self, task_id, prompt, workspace_path, on_event=None):
        (Path(workspace_path) / self._filename).write_text(self._content)
        return AgentResult(status="completed", output="done")


class _ConflictingAdapter:
    """Writes a divergent commit on base AND a conflicting file in the worktree,
    forcing a real add/add merge conflict on merge-back."""

    name = "claude-code"

    def run(self, task_id, prompt, workspace_path, on_event=None):
        worktree = Path(workspace_path)
        repo = worktree.parents[2]  # <repo>/.codeframe/worktrees/<task>
        # Divergent change landing on base while the agent worked.
        (repo / "conflict.txt").write_text("base version\n")
        _git(repo, "add", "conflict.txt")
        _git(repo, "commit", "-m", "base change")
        # Conflicting change in the worktree.
        (worktree / "conflict.txt").write_text("worktree version\n")
        return AgentResult(status="completed", output="done")


class _FailingAdapter:
    name = "claude-code"

    def run(self, task_id, prompt, workspace_path, on_event=None):
        (Path(workspace_path) / "partial.txt").write_text("partial work")
        return AgentResult(status="failed", error="boom")


def _run_with_adapter(git_workspace, adapter):
    """Start a run and execute it with a fake external adapter under worktree
    isolation, with gates stubbed to pass (isolates the merge-back wiring)."""
    task = tasks_mod.create(git_workspace, title="do a thing")
    run = runtime.start_task_run(git_workspace, task.id)

    gate_ok = MagicMock()
    gate_ok.passed = True

    with patch(
        "codeframe.core.engine_registry.get_external_adapter",
        return_value=adapter,
    ), patch(
        "codeframe.core.adapters.verification_wrapper.run_gates",
        return_value=gate_ok,
    ), patch(
        "codeframe.core.context_packager.TaskContextPackager.build",
        return_value=MagicMock(prompt="p", context=MagicMock()),
    ):
        state = runtime.execute_agent(
            git_workspace, run, engine="claude-code", isolation="worktree",
        )
    return task, state


class TestExecuteAgentWorktreeMergeBack:
    def test_success_merges_file_to_base_and_cleans_up(self, git_workspace: Workspace):
        task, state = _run_with_adapter(
            git_workspace, _FileWritingAdapter("agent_output.txt", "hello from agent"),
        )
        repo = git_workspace.repo_path

        assert state.status == AgentStatus.COMPLETED
        # Acceptance: file created by the adapter exists on the base branch.
        assert (repo / "agent_output.txt").exists()
        assert (repo / "agent_output.txt").read_text() == "hello from agent"
        # Merged → worktree + branch cleaned up.
        assert not _branch_exists(repo, f"cf/{task.id}")
        assert not (repo / ".codeframe" / "worktrees" / task.id).exists()
        # Single-run worktrees are intentionally never registered (so orphan
        # cleanup keyed on process liveness can't force-delete a preserved branch).
        from codeframe.core.worktrees import list_worktrees
        assert list_worktrees(repo) == []

    def test_conflict_creates_blocker_and_preserves_branch(self, git_workspace: Workspace):
        task, state = _run_with_adapter(git_workspace, _ConflictingAdapter())
        repo = git_workspace.repo_path

        # Acceptance: conflict → blocker, branch preserved.
        assert state.status == AgentStatus.BLOCKED
        task_blockers = blockers_mod.list_for_task(git_workspace, task.id)
        assert len(task_blockers) >= 1
        assert _branch_exists(repo, f"cf/{task.id}")
        assert (repo / ".codeframe" / "worktrees" / task.id).exists()

    def test_failed_run_preserves_branch(self, git_workspace: Workspace):
        task, state = _run_with_adapter(git_workspace, _FailingAdapter())
        repo = git_workspace.repo_path

        # Acceptance: run failure → branch preserved (no silent discard).
        assert state.status == AgentStatus.FAILED
        assert _branch_exists(repo, f"cf/{task.id}")


# ---------------------------------------------------------------------------
# Adapter threading of workspace_path (#715 / #716)
# ---------------------------------------------------------------------------


class TestBuiltinAdapterThreadsWorktree:
    """#715: the builtin react adapter builds its agent against workspace_path."""

    def test_react_agent_built_with_worktree_repo_path(self, git_workspace: Workspace):
        from codeframe.core.adapters.builtin import BuiltinReactAdapter

        worktree = git_workspace.repo_path / ".codeframe" / "worktrees" / "t1"
        adapter = BuiltinReactAdapter(git_workspace, MagicMock())

        with patch("codeframe.core.react_agent.ReactAgent") as MockAgent:
            MockAgent.return_value.run.return_value = AgentStatus.COMPLETED
            adapter.run("t1", "", worktree)

        built_ws = MockAgent.call_args.kwargs["workspace"]
        assert built_ws.repo_path == worktree
        # State DB stays on the main repo.
        assert built_ws.db_path == git_workspace.db_path

    def test_none_isolation_uses_original_workspace(self, git_workspace: Workspace):
        from codeframe.core.adapters.builtin import BuiltinReactAdapter

        adapter = BuiltinReactAdapter(git_workspace, MagicMock())
        with patch("codeframe.core.react_agent.ReactAgent") as MockAgent:
            MockAgent.return_value.run.return_value = AgentStatus.COMPLETED
            adapter.run("t1", "", git_workspace.repo_path)

        assert MockAgent.call_args.kwargs["workspace"] is git_workspace


class TestVerificationWrapperThreadsWorktree:
    """#716: gates run against the worktree, blockers against the main repo."""

    def test_gates_run_against_worktree_path(self, git_workspace: Workspace):
        from codeframe.core.adapters.verification_wrapper import VerificationWrapper

        worktree = git_workspace.repo_path / ".codeframe" / "worktrees" / "t1"
        inner = MagicMock()
        inner.name = "fake"
        inner.run.return_value = AgentResult(status="completed", output="ok")
        wrapper = VerificationWrapper(inner, git_workspace)

        gate_ok = MagicMock()
        gate_ok.passed = True
        with patch(
            "codeframe.core.adapters.verification_wrapper.run_gates",
            return_value=gate_ok,
        ) as mock_gates:
            wrapper.run("t1", "prompt", worktree)

        gate_ws = mock_gates.call_args.args[0]
        assert gate_ws.repo_path == worktree
        assert gate_ws.db_path == git_workspace.db_path
