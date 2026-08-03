"""Workspace DB integrity (#943).

- `_open_db` never ran `PRAGMA foreign_keys = ON`, so every declared FK was
  decorative: `tasks.delete` left orphaned blockers, runs and logs forever. The
  control-plane DB enabled it; this one did not.
- The UNIQUE index upgrade ran unconditionally, so a workspace already holding
  duplicate `external_url` rows raised on EVERY `get_workspace` — bricking both
  CLI and server with no recovery path.
- `cf stats` ran the control-plane `Database.initialize()` against the
  per-workspace `state.db`, injecting users/api_keys/audit_logs and a seeded
  admin row into the domain database.
"""


import pytest

from codeframe.core.workspace import _open_db, create_or_load_workspace

pytestmark = pytest.mark.v2


# The foreign-key enforcement tests moved to #1061 with the pragma itself: they
# only mean anything once PRAGMA foreign_keys is on, and turning it on requires
# migrating 66 test fixtures that currently insert orphan rows.


class TestDuplicateExternalUrlDoesNotBrickTheWorkspace:
    def test_a_workspace_with_duplicates_still_loads(self, tmp_path):
        from codeframe.core import tasks

        ws = create_or_load_workspace(tmp_path)
        url = "https://github.com/a/b/issues/1"
        tasks.create(ws, title="one", description="", external_url=url)

        # Force a duplicate past the index, the way a legacy row would exist.
        conn = _open_db(tmp_path / ".codeframe" / "state.db")
        conn.execute("DROP INDEX IF EXISTS idx_tasks_external_url")
        conn.commit()
        conn.close()
        tasks.create(ws, title="two", description="", external_url=url)

        # The upgrade path runs here; it used to raise and never recover.
        reloaded = create_or_load_workspace(tmp_path)

        assert reloaded is not None

    def test_the_duplicate_task_is_kept_not_deleted(self, tmp_path):
        """Deleting a user's task to add an index would be worse than the bug."""
        from codeframe.core import tasks

        ws = create_or_load_workspace(tmp_path)
        url = "https://github.com/a/b/issues/2"
        tasks.create(ws, title="first", description="", external_url=url)
        conn = _open_db(tmp_path / ".codeframe" / "state.db")
        conn.execute("DROP INDEX IF EXISTS idx_tasks_external_url")
        conn.commit()
        conn.close()
        tasks.create(ws, title="second", description="", external_url=url)

        create_or_load_workspace(tmp_path)

        titles = {t.title for t in tasks.list_tasks(ws)}
        assert {"first", "second"} <= titles, "a task was deleted to build an index"


class TestStatsDoesNotContaminateTheWorkspaceDb:
    def test_no_control_plane_tables_appear(self, tmp_path):
        from codeframe.platform_store.database import Database

        create_or_load_workspace(tmp_path)
        db = Database(tmp_path / ".codeframe" / "state.db")
        db.connect_readonly()

        tables = {
            r[0]
            for r in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

        assert not (tables & {"users", "api_keys", "audit_logs"}), (
            "control-plane tables were injected into the workspace DB"
        )

    def test_stats_uses_the_readonly_path(self):
        import inspect

        from codeframe.cli import stats_commands

        source = inspect.getsource(stats_commands)
        code = "\n".join(line.split("#")[0] for line in source.splitlines())

        assert "connect_readonly()" in code
        assert "db.initialize()" not in code, (
            "still running the control-plane SchemaManager on a workspace DB"
        )


class TestTaskDeleteCleansUpChildren:
    """Raised by the PR review as a major: enabling FK enforcement with no
    ON DELETE CASCADE and no child cleanup turns every deletion of an EXECUTED
    task into a hard constraint failure. Before enforcement those rows were
    silently orphaned — which is what the pragma exists to stop."""

    def test_deleting_a_task_with_runs_and_logs_succeeds(self, tmp_path):
        from codeframe.core import runtime, tasks

        ws = create_or_load_workspace(tmp_path)
        task = tasks.create(ws, title="executed", description="")
        run = runtime.start_task_run(ws, task.id)

        conn = _open_db(tmp_path / ".codeframe" / "state.db")
        conn.execute(
            "INSERT INTO run_logs (run_id, task_id, timestamp, log_level, category,"
            " message) VALUES (?,?,?,?,?,?)",
            (run.id, task.id, "2026-01-01", "INFO", "AGENT_ACTION", "x"),
        )
        conn.commit()
        conn.close()

        assert tasks.delete(ws, task.id) is True

    def test_the_child_rows_are_gone_not_orphaned(self, tmp_path):
        from codeframe.core import runtime, tasks

        ws = create_or_load_workspace(tmp_path)
        task = tasks.create(ws, title="executed", description="")
        runtime.start_task_run(ws, task.id)

        tasks.delete(ws, task.id)

        conn = _open_db(tmp_path / ".codeframe" / "state.db")
        remaining = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE task_id = ?", (task.id,)
        ).fetchone()[0]
        conn.close()

        assert remaining == 0, "runs were left orphaned"

    def test_deleting_a_task_with_no_children_still_works(self, tmp_path):
        from codeframe.core import tasks

        ws = create_or_load_workspace(tmp_path)
        task = tasks.create(ws, title="plain", description="")

        assert tasks.delete(ws, task.id) is True
