"""The per-test workspace schema build is the suite's cost centre (issue #979).

Rebuilding ~18 tables plus indexes per test costs ~1273ms on a real filesystem
(2.7ms on tmpfs) — that difference is fsync, and it is most of the wall clock
of a full local run. Copying a template built once per session costs 0.1ms.

The optimisation is only safe because ``_init_database`` is deterministic, so
these tests pin the property the speedup rests on rather than the speedup
itself. If a schema change ever made the output non-reproducible, the copy
would stop being equivalent and this file is what says so.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2


def _digest(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


class TestTheSchemaBuildIsReproducible:
    """The premise: two builds are byte-identical, so a copy is equivalent."""

    def test_two_builds_are_byte_identical(self, tmp_path, real_init_database):
        a, b = tmp_path / "a.sqlite", tmp_path / "b.sqlite"
        real_init_database(a)
        real_init_database(b)
        assert _digest(a) == _digest(b)

    def test_no_wal_sidecars_are_left_behind(self, tmp_path, real_init_database):
        """A single-file copy is only complete if -wal/-shm are checkpointed."""
        real_init_database(tmp_path / "db.sqlite")
        assert sorted(p.name for p in tmp_path.iterdir()) == ["db.sqlite"]


class TestTheTemplateMatchesARealBuild:
    """The guarantee: what tests get is what the real code path produces."""

    def test_the_copy_is_byte_identical_to_a_real_build(
        self, tmp_path, real_init_database
    ):
        from codeframe.core import workspace as ws

        real = tmp_path / "real.sqlite"
        real_init_database(real)

        copied = tmp_path / "copied.sqlite"
        ws._init_database(copied)  # the session-patched version

        assert _digest(copied) == _digest(real), (
            "the template has diverged from _init_database — the speedup is "
            "no longer equivalent to the real schema build"
        )

    def test_the_copy_carries_the_current_schema_version(self, tmp_path):
        """A SCHEMA_VERSION bump must not leave the template stamped behind."""
        from codeframe.core import workspace as ws

        db = tmp_path / "db.sqlite"
        ws._init_database(db)
        conn = sqlite3.connect(db)
        try:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == ws.SCHEMA_VERSION
        finally:
            conn.close()

    def test_the_copy_is_in_wal_mode(self, tmp_path):
        from codeframe.core import workspace as ws

        db = tmp_path / "db.sqlite"
        ws._init_database(db)
        conn = sqlite3.connect(db)
        try:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        finally:
            conn.close()

    @pytest.mark.parametrize("umask_value", [0o022, 0o002, 0o007])
    def test_the_copy_has_the_mode_sqlite_would_have_given_it(
        self, tmp_path, umask_value
    ):
        """A file copy carries the SOURCE's mode — that is the trap here.

        The template is built once under the session's umask, so copying its
        permission bits would hand every later test the wrong mode. Compared
        against a reference database sqlite creates itself, not a formula:
        sqlite uses an 0644 base, not open()'s 0666.
        """
        import os

        from codeframe.core import workspace as ws

        old = os.umask(umask_value)
        try:
            reference = tmp_path / "reference.db"
            sqlite3.connect(reference).close()
            expected = reference.stat().st_mode & 0o777

            db = tmp_path / "db.sqlite"
            ws._init_database(db)
            actual = db.stat().st_mode & 0o777
        finally:
            os.umask(old)

        assert actual == expected, f"mode {actual:o}, sqlite would give {expected:o}"

    def test_a_workspace_built_on_the_copy_works_end_to_end(self, tmp_path):
        """The point of the schema is that tasks round-trip through it."""
        from codeframe.core import tasks
        from codeframe.core.tasks import TaskStatus
        from codeframe.core.workspace import create_or_load_workspace

        repo = tmp_path / "repo"
        repo.mkdir()
        workspace = create_or_load_workspace(repo)
        task = tasks.create(workspace, title="T", description="d")
        tasks.update_status(workspace, task.id, TaskStatus.READY)

        assert tasks.get(workspace, task.id).status == TaskStatus.READY


class TestAnExistingDatabaseIsAMigration:
    """`_init_database` on an existing file tops it up — it does not rebuild.

    The template must only ever serve a *new* database. Copying over an
    existing one discards its contents and skips the schema work the caller
    asked for, which makes schema tests pass for the wrong reason: the
    template already has whatever they expected to be added.
    """

    def test_an_existing_database_keeps_its_data(self, tmp_path):
        from codeframe.core import workspace as ws

        db = tmp_path / "state.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE legacy (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO legacy VALUES ('keep-me')")
        conn.commit()
        conn.close()

        ws._init_database(db)

        conn = sqlite3.connect(db)
        try:
            assert conn.execute("SELECT id FROM legacy").fetchall() == [("keep-me",)]
        finally:
            conn.close()

    def test_a_missing_table_is_actually_created(self, tmp_path):
        """The concrete case: a database missing `blockers` gets the table.

        Was `test_the_alter_table_migration_actually_runs`, which watched a
        legacy `blockers` table gain `created_by`. #1104 moved every column
        migration to `_ensure_schema_upgrades`, so `_init_database` no longer
        performs that one — see `test_schema_alter_split_1104.py`. What this
        test is really for is unchanged: prove the REAL function ran and not a
        template copy, on a file that already exists.
        """
        from codeframe.core import workspace as ws

        db = tmp_path / "state.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE keepsake (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO keepsake VALUES ('k1')")
        conn.commit()
        conn.close()

        ws._init_database(db)

        conn = sqlite3.connect(db)
        try:
            tables = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            assert "blockers" in tables, "the template was copied instead"
            # Topped up, not replaced — a rebuild would have dropped the row.
            assert conn.execute("SELECT id FROM keepsake").fetchall() == [("k1",)]
        finally:
            conn.close()


class TestPerTestPatchingStillWins:
    """A test that swaps _init_database itself must not be broken by this."""

    def test_monkeypatch_restores_the_session_template_version(self, monkeypatch, tmp_path):
        from codeframe.core import workspace as ws

        patched = ws._init_database
        monkeypatch.setattr(ws, "_init_database", lambda p: None)
        assert ws._init_database is not patched
        monkeypatch.undo()
        assert ws._init_database is patched, (
            "undo must restore the template version, not the original"
        )
