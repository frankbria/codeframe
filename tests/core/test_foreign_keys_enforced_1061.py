"""The workspace schema's foreign keys are enforced, not decorative (#1061).

SQLite ignores every `FOREIGN KEY` clause unless `PRAGMA foreign_keys = ON` is
set **per connection**. `_open_db` never set it, so every FK in the workspace
schema did nothing: deleting a task left its blockers, runs, run_logs and
diagnostic_reports behind forever. The control-plane DB (`platform_store`) had
always enabled it; this one had not.

Turning it on is one line. The consequence was 66 failing tests across 7 files,
all the same cause: fixtures minted bare `uuid4()`s for `task_id`/`run_id` and
inserted child rows referencing them. **Those rows were being orphaned in
production** — the tests were asserting against a database state the schema
forbids. That is the finding, not an inconvenience, which is why the fixtures
were given real parent rows rather than the pragma being relaxed.

The child-row cleanup `tasks.delete` needs to survive enforcement (the FKs carry
no `ON DELETE CASCADE`) shipped in #943/#1059.
"""

import sqlite3
import subprocess

import pytest

from codeframe.core import runtime, tasks
from codeframe.core.workspace import create_or_load_workspace, get_db_connection

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=False)
    return create_or_load_workspace(tmp_path)


class TestThePragmaIsOn:
    def test_it_reads_back_as_enabled(self, workspace):
        conn = get_db_connection(workspace)
        try:
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        finally:
            conn.close()

    def test_every_connection_gets_it_not_just_the_first(self, workspace):
        """It is per-CONNECTION in SQLite, so setting it once at creation would
        leave every later connection unenforced — which is the whole trap."""
        for _ in range(3):
            conn = get_db_connection(workspace)
            try:
                assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            finally:
                conn.close()

    def test_a_reopened_workspace_still_has_it(self, workspace, tmp_path):
        reopened = create_or_load_workspace(tmp_path)

        conn = get_db_connection(reopened)
        try:
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        finally:
            conn.close()


class TestAnOrphanInsertIsRefused:
    """AC2 — asserted as behaviour, not by reading the pragma back. The pragma
    being 1 and the constraint actually firing are different claims."""

    def test_a_run_referencing_no_task_is_rejected(self, workspace):
        conn = get_db_connection(workspace)
        try:
            with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
                conn.execute(
                    "INSERT INTO runs (id, task_id, workspace_id, status, started_at)"
                    " VALUES (?,?,?,?,?)",
                    ("r1", "no-such-task", workspace.id, "RUNNING", "2026-01-01"),
                )
                conn.commit()
        finally:
            conn.close()

    def test_a_run_log_referencing_no_run_is_rejected(self, workspace):
        task = tasks.create(workspace, title="t", description="")
        conn = get_db_connection(workspace)
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO run_logs (run_id, task_id, timestamp, log_level,"
                    " category, message) VALUES (?,?,?,?,?,?)",
                    ("no-such-run", task.id, "2026-01-01", "INFO", "X", "m"),
                )
                conn.commit()
        finally:
            conn.close()

    def test_a_blocker_referencing_no_task_is_rejected(self, workspace):
        conn = get_db_connection(workspace)
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO blockers (id, workspace_id, task_id, question,"
                    " created_at) VALUES (?,?,?,?,?)",
                    ("b1", workspace.id, "no-such-task", "q?", "2026-01-01"),
                )
                conn.commit()
        finally:
            conn.close()

    def test_the_same_rows_are_accepted_with_real_parents(self, workspace):
        """The control. Without it, a schema that rejected everything would
        satisfy the three tests above."""
        task = tasks.create(workspace, title="t", description="")
        run = runtime.start_task_run(workspace, task.id)

        conn = get_db_connection(workspace)
        try:
            conn.execute(
                "INSERT INTO run_logs (run_id, task_id, timestamp, log_level,"
                " category, message) VALUES (?,?,?,?,?,?)",
                (run.id, task.id, "2026-01-01", "INFO", "X", "m"),
            )
            conn.execute(
                "INSERT INTO blockers (id, workspace_id, task_id, question,"
                " created_at) VALUES (?,?,?,?,?)",
                ("b1", workspace.id, task.id, "q?", "2026-01-01"),
            )
            conn.commit()
        finally:
            conn.close()

    def test_a_workspace_scoped_blocker_is_still_allowed(self, workspace):
        """`blockers.task_id` is NULLABLE, so a blocker not tied to a task must
        survive enforcement. A blanket NOT NULL would break `cf blocker` for
        workspace-level questions."""
        conn = get_db_connection(workspace)
        try:
            conn.execute(
                "INSERT INTO blockers (id, workspace_id, task_id, question,"
                " created_at) VALUES (?,?,?,?,?)",
                ("b-ws", workspace.id, None, "a workspace question", "2026-01-01"),
            )
            conn.commit()
        finally:
            conn.close()


class TestDeletingATaskStillWorksUnderEnforcement:
    """AC4. The FKs carry no ON DELETE CASCADE, so without the child cleanup
    that shipped in #943/#1059 enforcement turns every deletion of an executed
    task into a hard IntegrityError. This is the test that would have caught
    that, had the two changes landed in the other order."""

    def test_a_task_with_runs_logs_and_blockers_deletes_cleanly(self, workspace):
        task = tasks.create(workspace, title="executed", description="")
        run = runtime.start_task_run(workspace, task.id)

        conn = get_db_connection(workspace)
        conn.execute(
            "INSERT INTO run_logs (run_id, task_id, timestamp, log_level,"
            " category, message) VALUES (?,?,?,?,?,?)",
            (run.id, task.id, "2026-01-01", "INFO", "X", "m"),
        )
        conn.execute(
            "INSERT INTO blockers (id, workspace_id, task_id, question, created_at)"
            " VALUES (?,?,?,?,?)",
            ("b1", workspace.id, task.id, "q?", "2026-01-01"),
        )
        conn.commit()
        conn.close()

        assert tasks.delete(workspace, task.id) is True

        conn = get_db_connection(workspace)
        try:
            for table in ("runs", "run_logs", "blockers"):
                remaining = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                assert remaining == 0, f"{table} rows survived the delete"
        finally:
            conn.close()

    def test_clearing_a_workspace_works_too(self, workspace):
        for i in range(2):
            task = tasks.create(workspace, title=f"t{i}", description="")
            runtime.start_task_run(workspace, task.id)

        assert tasks.delete_all(workspace) == 2

        conn = get_db_connection(workspace)
        try:
            assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
        finally:
            conn.close()


class TestNoFixtureRelaxesTheEnforcement:
    """AC3's negative half. The migration had to give fixtures REAL parent rows;
    turning the pragma back off per-test, or deleting an assertion, would make
    the suite green while leaving the defect in place."""

    def test_no_test_leaves_the_pragma_off(self):
        """A bare OFF is the dangerous one.

        Disabling FKs around a truncate-every-table teardown is legitimate —
        rows cannot be deleted parent-first in arbitrary order — as long as it
        is turned back ON in the same file. What must not exist is an OFF with
        no matching ON, which silently opts a test out of the integrity the
        schema declares and lets an orphan-inserting fixture look green.
        """
        import re
        from pathlib import Path

        repo_root = Path(__file__).resolve().parent.parent.parent
        offenders = []
        for path in (repo_root / "tests").rglob("*.py"):
            if "node_modules" in path.parts:
                continue
            code = "\n".join(
                ln.split("#")[0] for ln in path.read_text(encoding="utf-8").splitlines()
            )
            offs = len(re.findall(r"foreign_keys\s*=\s*(?:OFF|off|0)", code))
            ons = len(re.findall(r"foreign_keys\s*=\s*(?:ON|on|1)", code))
            if offs > ons:
                offenders.append(f"{path.relative_to(repo_root)} ({offs} off, {ons} on)")

        assert not offenders, f"these leave FK enforcement disabled: {offenders}"

    def test_the_rule_would_catch_a_bare_disable(self, tmp_path):
        """A rule that cannot fail is worth nothing."""
        import re

        code = 'conn.execute("PRAGMA foreign_keys = OFF")'
        offs = len(re.findall(r"foreign_keys\s*=\s*(?:OFF|off|0)", code))
        ons = len(re.findall(r"foreign_keys\s*=\s*(?:ON|on|1)", code))

        assert offs > ons

    def test_the_source_enables_it_unconditionally(self):
        """Not behind an env var or a flag — that would let a deployment run
        without the integrity the schema declares."""
        import inspect

        from codeframe.core import workspace as ws_mod

        source = inspect.getsource(ws_mod._open_db)
        code = "\n".join(line.split("#")[0] for line in source.splitlines())

        assert 'PRAGMA foreign_keys = ON' in code
        assert "getenv" not in code
