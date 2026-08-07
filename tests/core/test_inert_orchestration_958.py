"""Inert orchestration features — wire or delete (issue #958).

Four defects, each a feature that exists but does nothing:

1. ``propagate_status`` had zero production callers, so composite parents
   created by ``cf tasks generate --recursive`` never rolled up. It also read
   children through ``list_tasks``' 100-task cap and would raise
   ``InvalidTransitionError`` for common propagations. **Wired**, because
   ``--recursive`` ships and ``cf tasks tree`` renders those parents.
2. ``run_engine_log`` was written with ``gates_passed=None`` /
   ``self_corrections=0``, so ``cf engines stats`` permanently rendered 0%
   Gate Pass and 0 self-corrections. **Wired** for the react engine, following
   the token-usage precedent from #932.
3. ``WorktreeRegistry.register`` was never called — ``sandbox/context.py``
   deliberately skips it, because orphan cleanup keyed on process liveness
   would force-delete a *preserved* branch. **Deleted**, along with its two
   always-empty callers; wiring it would reintroduce the bug that comment
   guards against.
4. ``TaskWorktree.cleanup`` ignored git exit codes, so a leftover
   ``cf/<task_id>`` branch failed the next run with no prior log. **Fixed.**
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.v2


# ─────────────────────────────────────────────────────────────────────────────
# 1. Composite parents roll up
# ─────────────────────────────────────────────────────────────────────────────


class TestParentStatusPropagation:
    def _tree(self, ws):
        """A composite parent with two atomic children."""
        from codeframe.core import tasks

        parent = tasks.create(ws, title="Parent", description="", is_leaf=False)
        c1 = tasks.create(ws, title="Child 1", description="", parent_id=parent.id)
        c2 = tasks.create(ws, title="Child 2", description="", parent_id=parent.id)
        return parent, c1, c2

    def _drive(self, ws, task_id, *statuses):
        from codeframe.core import tasks

        for s in statuses:
            tasks.update_status(ws, task_id, s)

    def test_all_children_done_rolls_parent_to_done(self, tmp_path):
        from codeframe.core import tasks
        from codeframe.core.tasks import TaskStatus
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        parent, c1, c2 = self._tree(ws)

        self._drive(ws, c1.id, TaskStatus.READY, TaskStatus.IN_PROGRESS, TaskStatus.DONE)
        # One child done is not enough.
        assert tasks.get(ws, parent.id).status != TaskStatus.DONE

        self._drive(ws, c2.id, TaskStatus.READY, TaskStatus.IN_PROGRESS, TaskStatus.DONE)
        assert tasks.get(ws, parent.id).status == TaskStatus.DONE

    def test_child_in_progress_rolls_parent_to_in_progress(self, tmp_path):
        from codeframe.core import tasks
        from codeframe.core.tasks import TaskStatus
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        parent, c1, _ = self._tree(ws)

        self._drive(ws, c1.id, TaskStatus.READY, TaskStatus.IN_PROGRESS)
        assert tasks.get(ws, parent.id).status == TaskStatus.IN_PROGRESS

    def test_propagation_walks_more_than_one_level(self, tmp_path):
        from codeframe.core import tasks
        from codeframe.core.tasks import TaskStatus
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        root = tasks.create(ws, title="Root", description="", is_leaf=False)
        mid = tasks.create(
            ws, title="Mid", description="", is_leaf=False, parent_id=root.id
        )
        leaf = tasks.create(ws, title="Leaf", description="", parent_id=mid.id)

        self._drive(
            ws, leaf.id, TaskStatus.READY, TaskStatus.IN_PROGRESS, TaskStatus.DONE
        )

        assert tasks.get(ws, mid.id).status == TaskStatus.DONE
        assert tasks.get(ws, root.id).status == TaskStatus.DONE

    def test_leaf_parent_is_not_rolled_up(self, tmp_path):
        """Only composite (is_leaf=False) parents aggregate."""
        from codeframe.core import tasks
        from codeframe.core.tasks import TaskStatus
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        parent = tasks.create(ws, title="Parent", description="")  # is_leaf=True
        child = tasks.create(ws, title="Child", description="", parent_id=parent.id)

        self._drive(
            ws, child.id, TaskStatus.READY, TaskStatus.IN_PROGRESS, TaskStatus.DONE
        )
        assert tasks.get(ws, parent.id).status == TaskStatus.BACKLOG

    def test_an_illegal_parent_transition_is_skipped_not_raised(self, tmp_path):
        """A rejected roll-up must never break the child's own transition.

        BACKLOG -> DONE is not an allowed transition, so a parent sitting in
        BACKLOG when its children finish used to make update_status raise.
        """
        from codeframe.core import tasks
        from codeframe.core.state_machine import ALLOWED_TRANSITIONS, TaskStatus
        from codeframe.core.workspace import create_or_load_workspace

        assert TaskStatus.DONE not in ALLOWED_TRANSITIONS[TaskStatus.BACKLOG], (
            "precondition: BACKLOG -> DONE must be illegal for this test to mean anything"
        )

        ws = create_or_load_workspace(tmp_path)
        parent = tasks.create(ws, title="Parent", description="", is_leaf=False)
        child = tasks.create(ws, title="Child", description="", parent_id=parent.id)

        # The child's own transition must succeed regardless.
        self._drive(
            ws, child.id, TaskStatus.READY, TaskStatus.IN_PROGRESS, TaskStatus.DONE
        )
        assert tasks.get(ws, child.id).status == TaskStatus.DONE

    def test_reopening_a_child_demotes_the_parent(self, tmp_path):
        """The roll-up must demote, not just promote (#958 review).

        DONE -> READY is a legal child transition. A roll-up that only knows
        how to promote leaves the parent stranded at DONE while a child is back
        in the queue.
        """
        from codeframe.core import tasks
        from codeframe.core.tasks import TaskStatus
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        parent, c1, c2 = self._tree(ws)
        for c in (c1, c2):
            self._drive(
                ws, c.id, TaskStatus.READY, TaskStatus.IN_PROGRESS, TaskStatus.DONE
            )
        assert tasks.get(ws, parent.id).status == TaskStatus.DONE

        # Reopen one child.
        tasks.update_status(ws, c1.id, TaskStatus.READY)
        assert tasks.get(ws, parent.id).status != TaskStatus.DONE

    def test_rolled_up_status_table(self):
        """The full mapping, including the partial-completion cases (#958 review).

        A parent with one DONE child and one still BACKLOG is *underway*, not
        un-started — falling through to BACKLOG reported finished work as never
        begun.
        """
        from codeframe.core.task_tree import _rolled_up_status
        from codeframe.core.tasks import TaskStatus as S

        cases = [
            ([], None),
            ([S.DONE, S.DONE], S.DONE),
            ([S.DONE, S.MERGED], S.DONE),
            ([S.DONE, S.FAILED], S.FAILED),
            ([S.DONE, S.IN_PROGRESS], S.IN_PROGRESS),
            ([S.DONE, S.BLOCKED], S.BLOCKED),
            ([S.DONE, S.BACKLOG], S.IN_PROGRESS),   # partial completion
            ([S.MERGED, S.BACKLOG], S.IN_PROGRESS),  # partial completion
            ([S.DONE, S.READY], S.IN_PROGRESS),     # partial completion
            ([S.READY, S.BACKLOG], S.READY),
            ([S.BACKLOG, S.BACKLOG], S.BACKLOG),
        ]
        for statuses, expected in cases:
            assert _rolled_up_status(list(statuses)) == expected, (
                f"{[s.value for s in statuses]} -> expected {expected}"
            )

    def test_partial_completion_does_not_demote_to_backlog(self, tmp_path):
        from codeframe.core import tasks
        from codeframe.core.tasks import TaskStatus
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        parent, c1, _c2 = self._tree(ws)

        # First child finishes; the second has not been touched.
        self._drive(
            ws, c1.id, TaskStatus.READY, TaskStatus.IN_PROGRESS, TaskStatus.DONE
        )
        assert tasks.get(ws, parent.id).status == TaskStatus.IN_PROGRESS

    def test_all_children_blocked_blocks_the_parent(self, tmp_path):
        from codeframe.core import tasks
        from codeframe.core.tasks import TaskStatus
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        parent, c1, c2 = self._tree(ws)
        for c in (c1, c2):
            self._drive(
                ws, c.id, TaskStatus.READY, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED
            )
        assert tasks.get(ws, parent.id).status == TaskStatus.BLOCKED

    def test_composites_never_enter_the_ready_execution_queue(self, tmp_path):
        """The is_leaf claim must be real now that parents can reach READY.

        Rolling a parent up to READY put it in `get_ready_task_ids` /
        `--all-ready`, which never filtered is_leaf — so a recursive tree would
        schedule the container alongside the child that holds the actual work.
        """
        from codeframe.core import runtime, tasks
        from codeframe.core.tasks import TaskStatus
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        parent, c1, c2 = self._tree(ws)

        tasks.update_status(ws, c1.id, TaskStatus.READY)
        tasks.update_status(ws, c2.id, TaskStatus.READY)

        # The roll-up is still correct...
        assert tasks.get(ws, parent.id).status == TaskStatus.READY
        # ...but the parent is not schedulable work.
        ready = runtime.get_ready_task_ids(ws)
        assert set(ready) == {c1.id, c2.id}
        assert parent.id not in ready

    def test_children_are_read_past_the_list_tasks_cap(self, tmp_path):
        """Children must be queried directly, not filtered out of a capped list."""
        from codeframe.core import task_tree, tasks
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        parent = tasks.create(ws, title="Parent", description="", is_leaf=False)
        for i in range(120):
            tasks.create(ws, title=f"C{i}", description="", parent_id=parent.id)

        children = task_tree._children_of(ws, parent.id)
        assert len(children) == 120

    def test_a_parent_cycle_terminates(self, tmp_path):
        """Corrupt parent links must not hang or blow the stack."""
        from codeframe.core import task_tree, tasks
        from codeframe.core.tasks import TaskStatus
        from codeframe.core.workspace import create_or_load_workspace, get_db_connection

        ws = create_or_load_workspace(tmp_path)
        a = tasks.create(ws, title="A", description="", is_leaf=False)
        b = tasks.create(ws, title="B", description="", is_leaf=False, parent_id=a.id)
        # Close the loop behind the API's back.
        conn = get_db_connection(ws)
        try:
            conn.execute(
                "UPDATE tasks SET parent_id = ? WHERE id = ?", (b.id, a.id)
            )
            conn.commit()
        finally:
            conn.close()

        # Must return rather than recurse forever.
        task_tree.propagate_status(ws, b.id)
        assert tasks.get(ws, a.id).status in set(TaskStatus)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Engine stats carry real gate / self-correction numbers
# ─────────────────────────────────────────────────────────────────────────────


class TestEngineStatsAreReal:
    def test_agent_result_carries_the_fields(self):
        from codeframe.core.adapters.agent_adapter import AgentResult

        fields = AgentResult.__dataclass_fields__
        assert "gates_passed" in fields
        assert "self_corrections" in fields

    def test_builtin_adapter_copies_them_off_the_agent(self):
        from codeframe.core.adapters.builtin import BuiltinReactAdapter
        from codeframe.core.agent import AgentStatus

        class FakeAgent:
            gates_passed = True
            self_correction_count = 3
            cost_tracker = None

        result = BuiltinReactAdapter._map_status(AgentStatus.COMPLETED, FakeAgent())
        assert result.gates_passed is True
        assert result.self_corrections == 3

    def test_missing_attributes_degrade_to_none_not_crash(self):
        from codeframe.core.adapters.builtin import BuiltinReactAdapter
        from codeframe.core.agent import AgentStatus

        class Bare:
            cost_tracker = None

        result = BuiltinReactAdapter._map_status(AgentStatus.COMPLETED, Bare())
        assert result.gates_passed is None
        assert result.self_corrections == 0

    def _wrapper(self, ws, inner, gate_outcomes):
        """VerificationWrapper over ``inner`` with a scripted gate sequence."""
        from codeframe.core.adapters.verification_wrapper import VerificationWrapper
        from codeframe.core.gates import GateResult

        wrapper = VerificationWrapper(inner, ws, max_correction_rounds=2)
        outcomes = list(gate_outcomes)

        def fake_gates(*a, **kw):
            return GateResult(passed=outcomes.pop(0), checks=[])

        return wrapper, fake_gates

    def test_wrapper_stamps_a_passing_external_run(self, tmp_path):
        """External engines run gates in the wrapper, not the agent (#958 review)."""
        from codeframe.core.adapters import verification_wrapper as vw
        from codeframe.core.adapters.agent_adapter import AgentResult
        from codeframe.core.workspace import create_or_load_workspace

        class Inner:
            name = "fake"

            def run(self, *a, **kw):
                return AgentResult(status="completed", output="ok")

        ws = create_or_load_workspace(tmp_path)
        wrapper, fake_gates = self._wrapper(ws, Inner(), [True])
        with patch.object(vw, "run_gates", fake_gates):
            result = wrapper.run("t1", "prompt", tmp_path)

        assert result.gates_passed is True
        assert result.self_corrections == 0

    def test_wrapper_leaves_gates_unknown_when_they_never_ran(self, tmp_path):
        """A failed adapter run is not a failed gate run."""
        from codeframe.core.adapters.agent_adapter import AgentResult
        from codeframe.core.adapters.verification_wrapper import VerificationWrapper
        from codeframe.core.workspace import create_or_load_workspace

        class Inner:
            name = "fake"

            def run(self, *a, **kw):
                return AgentResult(status="failed", error="boom")

        ws = create_or_load_workspace(tmp_path)
        result = VerificationWrapper(Inner(), ws).run("t1", "prompt", tmp_path)

        assert result.gates_passed is None
        assert result.self_corrections == 0

    def test_runtime_forwards_them_to_record_run(self):
        """runtime must stop hardcoding None/0."""
        import inspect

        from codeframe.core import runtime

        source = inspect.getsource(runtime.execute_agent)
        assert "gates_passed=None" not in source
        assert "self_corrections=0," not in source

    def test_stats_report_a_real_gate_pass_rate(self, tmp_path):
        from codeframe.core import engine_stats
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        for i, passed in enumerate([True, True, False]):
            engine_stats.record_run(
                workspace=ws,
                run_id=f"r{i}",
                engine="react",
                task_id=f"t{i}",
                status="COMPLETED",
                duration_ms=10,
                tokens_used=5,
                gates_passed=1 if passed else 0,
                self_corrections=i,
            )

        react = engine_stats.get_engine_stats(ws)["react"]
        # 2 of 3 runs passed gates; rates are percentages.
        assert react["gate_pass_rate"] == pytest.approx(66.67, abs=0.01)
        # 2 of 3 runs had self_corrections > 0 (i == 1 and i == 2).
        assert react["self_correction_rate"] == pytest.approx(66.67, abs=0.01)


# ─────────────────────────────────────────────────────────────────────────────
# 3. The always-empty worktree registry is gone
# ─────────────────────────────────────────────────────────────────────────────


class TestWorktreeRegistryRemoved:
    def test_registry_symbol_is_gone(self):
        import codeframe.core.worktrees as wt

        assert not hasattr(wt, "WorktreeRegistry")
        assert not hasattr(wt, "list_worktrees")

    def test_no_live_references_remain_in_production_code(self):
        """Prose explaining the removal is fine; code using it is not.

        Walks the AST rather than grepping, so comments and docstrings that
        document *why* the registry went away don't count as usage.
        """
        import ast

        import codeframe

        dead = {"WorktreeRegistry", "list_worktrees", "cleanup_stale", "list_stale"}
        root = Path(codeframe.__file__).parent
        hits = []
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            for node in ast.walk(tree):
                found = None
                if isinstance(node, ast.Name) and node.id in dead:
                    found = node.id
                elif isinstance(node, ast.Attribute) and node.attr in dead:
                    found = node.attr
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.name in dead:
                            found = alias.name
                if found:
                    hits.append(f"{path.relative_to(root)}:{node.lineno}: {found}")
        assert hits == [], f"live registry references: {hits}"

    def test_doctor_lists_leftover_dirs_and_scopes_the_hint_to_the_project(
        self, tmp_path, capsys
    ):
        """`env doctor --project X` must not print a hint that hits the cwd repo."""
        from codeframe.cli import env_commands
        from codeframe.core.worktrees import WORKTREE_DIR

        project = tmp_path / "elsewhere"
        (project / WORKTREE_DIR / "task-abc").mkdir(parents=True)

        try:
            env_commands.doctor(project=str(project))
        except Exception:
            pass  # Only the worktree panel is under test.

        # Rich hard-wraps the console, so collapse whitespace before matching.
        out = " ".join(capsys.readouterr().out.split())
        assert "task-abc" in out
        # The remediation must name the inspected repo, not a bare relative path.
        assert f"git -C {project}" in out

    def test_sandbox_reexports_do_not_break(self):
        """The package must still import cleanly after the removal."""
        from codeframe.core.sandbox import TaskWorktree  # noqa: F401
        import codeframe.core.sandbox as sandbox
        import codeframe.core.sandbox.worktree as sandbox_worktree

        assert "WorktreeRegistry" not in sandbox.__all__
        assert "WorktreeRegistry" not in sandbox_worktree.__all__


# ─────────────────────────────────────────────────────────────────────────────
# 4. cleanup() reports git failures
# ─────────────────────────────────────────────────────────────────────────────


class TestCleanupLogsGitFailures:
    def test_nonzero_worktree_remove_is_logged_with_stderr(self, tmp_path, caplog):
        from codeframe.core.worktrees import TaskWorktree

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                cmd, returncode=128, stdout="", stderr="fatal: is not a working tree"
            )

        with patch("subprocess.run", side_effect=fake_run):
            with caplog.at_level("WARNING"):
                TaskWorktree().cleanup(tmp_path, "task-1")

        assert "fatal: is not a working tree" in caplog.text

    def test_nonzero_branch_delete_is_logged_with_stderr(self, tmp_path, caplog):
        from codeframe.core.worktrees import TaskWorktree

        def fake_run(cmd, **kwargs):
            rc = 1 if "branch" in cmd else 0
            return subprocess.CompletedProcess(
                cmd,
                returncode=rc,
                stdout="",
                stderr="error: branch 'cf/task-1' not found" if rc else "",
            )

        with patch("subprocess.run", side_effect=fake_run):
            with caplog.at_level("WARNING"):
                TaskWorktree().cleanup(tmp_path, "task-1")

        assert "cf/task-1" in caplog.text

    def test_clean_run_logs_nothing(self, tmp_path, caplog):
        from codeframe.core.worktrees import TaskWorktree

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            with caplog.at_level("WARNING"):
                TaskWorktree().cleanup(tmp_path, "task-1")

        assert caplog.text.strip() == ""

    def test_cleanup_still_never_raises(self, tmp_path, caplog):
        from codeframe.core.worktrees import TaskWorktree

        with patch("subprocess.run", side_effect=OSError("git missing")):
            with caplog.at_level("WARNING"):
                TaskWorktree().cleanup(tmp_path, "task-1")  # must not raise

        assert "git missing" in caplog.text
