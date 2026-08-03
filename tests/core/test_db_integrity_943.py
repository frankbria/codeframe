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


# The foreign-key enforcement tests live in test_foreign_keys_enforced_1061.py,
# which is where the pragma was turned on. The child-row cleanup below is what
# makes enforcement survivable — the FKs carry no ON DELETE CASCADE — so the two
# files are the two halves of one guarantee.


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


#: Every table the cleanup must reach, with a row keyed to a run or a task.
#: The columns are the NOT NULL ones; anything nullable is left out.
def _seed_every_child_table(db_path, task_id: str, run_id: str, workspace_id: str) -> None:
    conn = _open_db(db_path)
    conn.execute(
        "INSERT INTO run_logs (run_id, task_id, timestamp, log_level, category,"
        " message) VALUES (?,?,?,?,?,?)",
        (run_id, task_id, "2026-01-01", "INFO", "AGENT_ACTION", "x"),
    )
    conn.execute(
        "INSERT INTO diagnostic_reports (id, task_id, run_id, root_cause,"
        " failure_category, severity, recommendations, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (f"diag-{run_id}", task_id, run_id, "x", "y", "low", "[]", "2026-01-01"),
    )
    conn.execute(
        "INSERT INTO blockers (id, workspace_id, task_id, question, created_at)"
        " VALUES (?,?,?,?,?)",
        (f"blk-{run_id}", workspace_id, task_id, "q?", "2026-01-01"),
    )
    step_id = f"step-{run_id}"
    conn.execute(
        "INSERT INTO execution_steps (id, run_id, step_number, step_type,"
        " description, started_at) VALUES (?,?,?,?,?,?)",
        (step_id, run_id, 1, "edit", "x", "2026-01-01"),
    )
    conn.execute(
        "INSERT INTO llm_interactions (id, run_id, step_id, prompt, response,"
        " model, timestamp) VALUES (?,?,?,?,?,?,?)",
        (f"llm-{run_id}", run_id, step_id, "p", "r", "m", "2026-01-01"),
    )
    conn.execute(
        "INSERT INTO file_operations (id, run_id, step_id, operation_type,"
        " file_path, timestamp) VALUES (?,?,?,?,?,?)",
        (f"fo-{run_id}", run_id, step_id, "edit", "a.py", "2026-01-01"),
    )
    conn.execute(
        "INSERT INTO run_engine_log (run_id, engine, task_id, workspace_id,"
        " status, created_at) VALUES (?,?,?,?,?,?)",
        (run_id, "react", task_id, workspace_id, "done", "2026-01-01"),
    )
    conn.execute(
        "INSERT INTO cloud_run_metadata (run_id, sandbox_minutes,"
        " cost_usd_estimate, files_uploaded, files_downloaded,"
        " credential_scan_blocked, created_at) VALUES (?,?,?,?,?,?,?)",
        (run_id, 1.0, 0.1, 1, 1, 0, "2026-01-01"),
    )
    conn.commit()
    conn.close()


#: Checked after each deletion. run_engine_log and cloud_run_metadata declare
#: no FK, but key off the same ids and orphan identically.
_CHILD_TABLES = (
    "run_logs",
    "diagnostic_reports",
    "execution_steps",
    "llm_interactions",
    "file_operations",
    "run_engine_log",
    "cloud_run_metadata",
    "runs",
    "blockers",
)


def _remaining_rows(db_path) -> dict[str, int]:
    conn = _open_db(db_path)
    try:
        return {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in _CHILD_TABLES
        }
    finally:
        conn.close()


class TestEveryDescendantTableIsCleaned:
    """Three more review findings. The first cut cleaned run_logs,
    diagnostic_reports, runs and blockers — but `runs` has three further FK
    dependents (execution_steps, llm_interactions, file_operations), and
    run_logs was matched on run_id alone although it declares a task_id FK
    too."""

    def test_no_table_keeps_a_row_after_the_task_is_deleted(self, tmp_path):
        from codeframe.core import runtime, tasks

        ws = create_or_load_workspace(tmp_path)
        task = tasks.create(ws, title="executed", description="")
        run = runtime.start_task_run(ws, task.id)
        db = tmp_path / ".codeframe" / "state.db"
        _seed_every_child_table(db, task.id, run.id, ws.id)

        assert all(v > 0 for v in _remaining_rows(db).values()), "seed failed"

        tasks.delete(ws, task.id)

        leftovers = {t: n for t, n in _remaining_rows(db).items() if n}
        assert not leftovers, f"orphaned rows survived: {leftovers}"

    def test_a_run_log_whose_run_is_already_gone_is_still_removed(self, tmp_path):
        """Matched on task_id, not only through `runs`. These orphans predate
        the fix and would block FK enforcement (#1061) forever otherwise."""
        from codeframe.core import tasks

        ws = create_or_load_workspace(tmp_path)
        task = tasks.create(ws, title="t", description="")
        db = tmp_path / ".codeframe" / "state.db"

        # This orphan can no longer be CREATED — foreign keys are enforced
        # (#1061) — but it is exactly what pre-enforcement workspaces contain,
        # and cleaning it up is what this test is about. Constructed
        # deliberately, with the pragma turned back on in the same block.
        conn = _open_db(db)
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            "INSERT INTO run_logs (run_id, task_id, timestamp, log_level,"
            " category, message) VALUES (?,?,?,?,?,?)",
            ("run-that-never-existed", task.id, "2026-01-01", "INFO", "X", "m"),
        )
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()

        tasks.delete(ws, task.id)

        assert _remaining_rows(db)["run_logs"] == 0


class TestDeleteAllCleansUpToo:
    """The sibling `delete_all` had no child cleanup at all, so clearing a
    workspace left every run, log and blocker of every task behind."""

    def test_clearing_a_workspace_leaves_no_child_rows(self, tmp_path):
        from codeframe.core import runtime, tasks

        ws = create_or_load_workspace(tmp_path)
        db = tmp_path / ".codeframe" / "state.db"
        for i in range(2):
            task = tasks.create(ws, title=f"t{i}", description="")
            run = runtime.start_task_run(ws, task.id)
            _seed_every_child_table(db, task.id, run.id, ws.id)

        assert tasks.delete_all(ws) == 2

        leftovers = {t: n for t, n in _remaining_rows(db).items() if n}
        assert not leftovers, f"orphaned rows survived delete_all: {leftovers}"

    def test_an_empty_workspace_is_a_no_op(self, tmp_path):
        from codeframe.core import tasks

        ws = create_or_load_workspace(tmp_path)

        assert tasks.delete_all(ws) == 0

    def test_another_workspaces_rows_are_untouched(self, tmp_path):
        """delete_all scopes children through the tasks table, so it must not
        reach past its own workspace_id."""
        from codeframe.core import runtime, tasks

        (tmp_path / "keep").mkdir()
        (tmp_path / "drop").mkdir()
        keep = create_or_load_workspace(tmp_path / "keep")
        kept_task = tasks.create(keep, title="keep", description="")
        runtime.start_task_run(keep, kept_task.id)

        drop = create_or_load_workspace(tmp_path / "drop")
        tasks.create(drop, title="drop", description="")
        tasks.delete_all(drop)

        assert _remaining_rows(tmp_path / "keep" / ".codeframe" / "state.db")["runs"] == 1
