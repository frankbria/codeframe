"""cloud_timeout_minutes plumbing + manual-dependency preservation (issue #959).

Two defects:

1. ``start_batch``/``create_batch`` accept ``cloud_timeout_minutes`` and the CLI
   passes it, but it was never stored on ``BatchRun`` nor forwarded to
   ``_execute_task_subprocess`` — so the callee default of 30 always won and
   ``cf work batch run --engine cloud --cloud-timeout 60`` was silently
   ignored, including after a resume.
2. ``apply_inferred_dependencies``' docstring promised it preserves existing
   manual dependencies, but ``update_depends_on`` replaces ``depends_on``
   wholesale — so under ``--strategy auto`` a hand-curated dependency was
   silently replaced by the LLM-inferred one and persisted for every future
   run.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.v2


def _utc_now():
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# 1. cloud_timeout_minutes reaches the child command
# ─────────────────────────────────────────────────────────────────────────────


class TestCloudTimeoutPlumbing:
    def test_batchrun_carries_the_field(self):
        from codeframe.core.conductor import BatchRun

        assert "cloud_timeout_minutes" in BatchRun.__dataclass_fields__

    def test_create_batch_persists_the_user_value(self, tmp_path):
        from codeframe.core import tasks
        from codeframe.core.conductor import create_batch, get_batch
        from codeframe.core.tasks import TaskStatus
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        t = tasks.create(ws, title="T", description="")
        tasks.update_status(ws, t.id, TaskStatus.READY)

        batch = create_batch(
            ws, task_ids=[t.id], engine="cloud", isolation="none",
            cloud_timeout_minutes=60,
        )
        assert batch.cloud_timeout_minutes == 60

        # Survives the round trip — resume must restore it.
        reloaded = get_batch(ws, batch.id)
        assert reloaded.cloud_timeout_minutes == 60

    def test_default_is_still_30(self, tmp_path):
        from codeframe.core import tasks
        from codeframe.core.conductor import create_batch, get_batch
        from codeframe.core.tasks import TaskStatus
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        t = tasks.create(ws, title="T", description="")
        tasks.update_status(ws, t.id, TaskStatus.READY)

        batch = create_batch(ws, task_ids=[t.id], engine="cloud")
        assert get_batch(ws, batch.id).cloud_timeout_minutes == 30

    def test_existing_workspace_gets_the_column_on_upgrade(self, tmp_path):
        """A DB already stamped at the previous SCHEMA_VERSION must migrate.

        `_ensure_schema_upgrades` returns early once user_version reaches
        SCHEMA_VERSION, so adding a migration entry without bumping the version
        leaves existing workspaces without the column — and every batch SELECT,
        which now names it unconditionally, dies. (Learned the hard way in #957.)
        """
        from codeframe.core import tasks
        from codeframe.core.conductor import create_batch, get_batch
        from codeframe.core.tasks import TaskStatus
        from codeframe.core.workspace import create_or_load_workspace, get_db_connection

        ws = create_or_load_workspace(tmp_path)
        t = tasks.create(ws, title="T", description="")
        tasks.update_status(ws, t.id, TaskStatus.READY)
        batch = create_batch(ws, task_ids=[t.id], cloud_timeout_minutes=55)

        # Roll back to the pre-#959 shape.
        conn = get_db_connection(ws)
        try:
            conn.execute("ALTER TABLE batch_runs DROP COLUMN cloud_timeout_minutes")
            conn.execute("PRAGMA user_version = 3")
            conn.commit()
        finally:
            conn.close()

        ws2 = create_or_load_workspace(tmp_path)
        reloaded = get_batch(ws2, batch.id)
        assert reloaded is not None
        # Column re-added with its default; the old value is gone, which is
        # expected — the point is that reads do not blow up.
        assert reloaded.cloud_timeout_minutes == 30

    def test_every_subprocess_call_site_forwards_it(self):
        """All seven call sites must pass batch.cloud_timeout_minutes."""
        import inspect

        from codeframe.core import conductor

        source = inspect.getsource(conductor)
        # Exclude the definition itself.
        calls = source.count("_execute_task_subprocess(\n") - source.count(
            "def _execute_task_subprocess(\n"
        )
        forwards = source.count("cloud_timeout_minutes=batch.cloud_timeout_minutes")
        assert calls == 7, f"call-site count changed: {calls}"
        assert forwards == calls, (
            f"{calls} call sites but {forwards} forward cloud_timeout_minutes"
        )

    def test_child_command_carries_the_value_after_a_resume(self, tmp_path):
        """The acceptance criterion: resume must not silently fall back to 30."""
        from codeframe.core import conductor, tasks
        from codeframe.core.conductor import BatchStatus, create_batch, resume_batch
        from codeframe.core.tasks import TaskStatus
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        t = tasks.create(ws, title="T", description="")
        tasks.update_status(ws, t.id, TaskStatus.READY)

        batch = create_batch(
            ws, task_ids=[t.id], engine="cloud", cloud_timeout_minutes=45,
        )
        # Mark it FAILED so resume has something to re-run.
        batch.status = BatchStatus.FAILED
        batch.results = {t.id: "FAILED"}
        conductor._save_batch(ws, batch)

        seen: list[list[str]] = []

        def fake_popen(cmd, **kwargs):
            seen.append(cmd)
            raise RuntimeError("stop here — the command line is what we assert on")

        with patch("subprocess.Popen", side_effect=fake_popen):
            try:
                resume_batch(ws, batch.id)
            except Exception:
                pass

        assert seen, "expected a child process to be launched"
        cmd = seen[0]
        assert "--cloud-timeout" in cmd
        assert cmd[cmd.index("--cloud-timeout") + 1] == "45"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Manual dependencies survive inference
# ─────────────────────────────────────────────────────────────────────────────


class TestManualDependenciesSurvive:
    def _three_tasks(self, ws):
        from codeframe.core import tasks

        a = tasks.create(ws, title="A", description="")
        b = tasks.create(ws, title="B", description="")
        c = tasks.create(ws, title="C", description="")
        return a, b, c

    def test_manual_dependency_is_not_replaced(self, tmp_path):
        from codeframe.core import tasks
        from codeframe.core.dependency_analyzer import apply_inferred_dependencies
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        a, b, c = self._three_tasks(ws)

        # Hand-curated: C depends on A.
        tasks.update_depends_on(ws, c.id, [a.id])
        # The LLM infers C depends on B instead.
        apply_inferred_dependencies(ws, {c.id: [b.id]})

        deps = set(tasks.get(ws, c.id).depends_on)
        assert a.id in deps, "manual dependency was wiped"
        assert b.id in deps, "inferred dependency was not applied"

    def test_inference_still_applies_when_there_are_no_manual_deps(self, tmp_path):
        from codeframe.core import tasks
        from codeframe.core.dependency_analyzer import apply_inferred_dependencies
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        a, b, c = self._three_tasks(ws)

        apply_inferred_dependencies(ws, {c.id: [a.id, b.id]})
        assert set(tasks.get(ws, c.id).depends_on) == {a.id, b.id}

    def test_no_duplicates_when_inference_repeats_a_manual_dep(self, tmp_path):
        from codeframe.core import tasks
        from codeframe.core.dependency_analyzer import apply_inferred_dependencies
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        a, _b, c = self._three_tasks(ws)

        tasks.update_depends_on(ws, c.id, [a.id])
        apply_inferred_dependencies(ws, {c.id: [a.id]})

        assert tasks.get(ws, c.id).depends_on == [a.id]

    def test_empty_inference_leaves_manual_deps_alone(self, tmp_path):
        from codeframe.core import tasks
        from codeframe.core.dependency_analyzer import apply_inferred_dependencies
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        a, _b, c = self._three_tasks(ws)

        tasks.update_depends_on(ws, c.id, [a.id])
        apply_inferred_dependencies(ws, {c.id: []})

        assert tasks.get(ws, c.id).depends_on == [a.id]

    def test_an_inferred_edge_that_would_cycle_is_dropped(self, tmp_path, caplog):
        """Merging can create a cycle that replacing would not.

        Manual A->B plus inferred B->A is a cycle even though neither set has
        one alone. The manual edge is user intent, so the *inferred* edge loses.
        """
        from codeframe.core import tasks
        from codeframe.core.dependency_analyzer import apply_inferred_dependencies
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        a, b, _c = self._three_tasks(ws)

        tasks.update_depends_on(ws, a.id, [b.id])  # manual: A depends on B

        with caplog.at_level("WARNING"):
            apply_inferred_dependencies(ws, {b.id: [a.id]})  # inferred: B on A

        assert tasks.get(ws, a.id).depends_on == [b.id], "manual edge must survive"
        assert tasks.get(ws, b.id).depends_on == [], "cyclic inferred edge must drop"
        assert "cycle" in caplog.text.lower()

    def test_a_preexisting_unrelated_cycle_does_not_block_valid_edges(self, tmp_path):
        """The guard must blame the edge being added, not any cycle anywhere.

        `update_depends_on` performs no cycle validation, so a workspace can
        already hold one. A whole-graph cycle detector would return that
        pre-existing cycle for every inferred edge — dropping valid, unrelated
        edges and misattributing the cause in the warning.
        """
        from codeframe.core import tasks
        from codeframe.core.dependency_analyzer import apply_inferred_dependencies
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        a, b, c = self._three_tasks(ws)
        d = tasks.create(ws, title="D", description="")

        # Pre-existing A <-> B cycle, persisted directly (no validation stops it).
        tasks.update_depends_on(ws, a.id, [b.id])
        tasks.update_depends_on(ws, b.id, [a.id])

        # An unrelated inferred edge C -> D must still be applied.
        apply_inferred_dependencies(ws, {c.id: [d.id]})

        assert tasks.get(ws, c.id).depends_on == [d.id]
        # The pre-existing cycle is left exactly as it was.
        assert tasks.get(ws, a.id).depends_on == [b.id]
        assert tasks.get(ws, b.id).depends_on == [a.id]

    def test_a_longer_cycle_is_still_caught(self, tmp_path):
        """A -> B -> C plus inferred C -> A closes a three-node cycle."""
        from codeframe.core import tasks
        from codeframe.core.dependency_analyzer import apply_inferred_dependencies
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        a, b, c = self._three_tasks(ws)

        tasks.update_depends_on(ws, a.id, [b.id])
        tasks.update_depends_on(ws, b.id, [c.id])

        apply_inferred_dependencies(ws, {c.id: [a.id]})

        assert tasks.get(ws, c.id).depends_on == [], "cyclic edge should be dropped"

    def test_docstring_matches_behaviour(self):
        from codeframe.core.dependency_analyzer import apply_inferred_dependencies

        doc = apply_inferred_dependencies.__doc__ or ""
        assert "merge" in doc.lower() or "preserv" in doc.lower()
