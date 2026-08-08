"""A fresh workspace and an upgraded one must end up with the same schema (#1060).

`workspace.py` carried 28 `CREATE TABLE IF NOT EXISTS` statements copy-pasted
between `_init_database` (fresh) and `_ensure_schema_upgrades` (existing), and
they had already drifted: 6 tables and 5 indexes existed only on the create
path, 1 table only on the upgrade path.

Drift like that is invisible until someone hits the less-exercised path at
runtime. These tests make it impossible rather than merely unlikely — the
generic one below drops each table in turn and asserts the upgrade path
rebuilds it identically, so a new table added to only one path fails here.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2


def _schema(db_path: Path) -> dict[str, str]:
    """Every object in sqlite_master, normalised for comparison."""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    finally:
        conn.close()
    return {
        f"{kind}:{name}": " ".join((sql or "").split())
        for kind, name, sql in rows
    }


def _fresh(tmp_path: Path) -> Path:
    from codeframe.core.workspace import _init_database

    db = tmp_path / "fresh.db"
    _init_database(db)
    return db


def _all_tables(db_path: Path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        return sorted(
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            )
        )
    finally:
        conn.close()


def _make_legacy(db_path: Path, drop: list[str]) -> None:
    """Simulate an older workspace: drop tables and un-stamp the version."""
    conn = sqlite3.connect(db_path)
    try:
        for table in drop:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.execute("PRAGMA user_version = 0")
        conn.commit()
    finally:
        conn.close()


class TestEveryTableIsRebuiltByTheUpgradePath:
    """The generic guard: no table may exist on only one path."""

    def test_each_table_dropped_alone_is_restored(self, tmp_path):
        from codeframe.core.workspace import _ensure_schema_upgrades, _init_database

        reference = _schema(_fresh(tmp_path))
        missing: dict[str, list[str]] = {}

        for table in _all_tables(tmp_path / "fresh.db"):
            db = tmp_path / f"upg_{table}.db"
            _init_database(db)
            _make_legacy(db, [table])
            _ensure_schema_upgrades(db)

            after = _schema(db)
            gone = sorted(set(reference) - set(after))
            if gone:
                missing[table] = gone

        assert missing == {}, (
            "the upgrade path does not rebuild these — a fresh workspace and "
            f"an upgraded one would diverge: {missing}"
        )

    def test_dropping_everything_rebuilds_the_whole_schema(self, tmp_path):
        """The strongest form: an empty DB upgraded == a fresh one."""
        from codeframe.core.workspace import _ensure_schema_upgrades, _init_database

        reference = _schema(_fresh(tmp_path))

        db = tmp_path / "empty.db"
        _init_database(db)
        _make_legacy(db, _all_tables(db))
        _ensure_schema_upgrades(db)

        assert sorted(_schema(db)) == sorted(reference)


class TestNoDdlIsDuplicated:
    """AC1 — each table's DDL exists in exactly one place."""

    def test_no_create_table_statement_appears_twice(self):
        import re

        source = Path("codeframe/core/workspace.py").read_text()
        names = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", source)
        duplicated = sorted({n for n in names if names.count(n) > 1})
        assert duplicated == [], (
            f"DDL duplicated between the create and upgrade paths: {duplicated}"
        )

    def test_no_create_index_statement_appears_twice(self):
        """Indexes are DDL too — the first version of this guard missed them.

        Harmless at runtime (IF NOT EXISTS, and the one UNIQUE index is
        guarded), but "each table's DDL exists in exactly one place" is the
        acceptance criterion, and a duplicate index is the same drift hazard
        one level down.
        """
        import re

        source = Path("codeframe/core/workspace.py").read_text()
        names = re.findall(r"CREATE (?:UNIQUE )?INDEX IF NOT EXISTS (\w+)", source)
        duplicated = sorted({n for n in names if names.count(n) > 1})
        assert duplicated == [], f"index DDL duplicated: {duplicated}"


class TestNoBehaviourChange:
    """AC3 — existing workspaces still open, new ones still initialise."""

    def test_a_new_workspace_initialises(self, tmp_path):
        from codeframe.core import tasks
        from codeframe.core.workspace import create_or_load_workspace

        repo = tmp_path / "repo"
        repo.mkdir()
        ws = create_or_load_workspace(repo)
        assert tasks.create(ws, title="T", description="d").id

    def test_an_existing_workspace_reopens_with_its_data(self, tmp_path):
        from codeframe.core import tasks
        from codeframe.core.workspace import create_or_load_workspace

        repo = tmp_path / "repo"
        repo.mkdir()
        first = create_or_load_workspace(repo)
        task = tasks.create(first, title="keep me", description="d")

        again = create_or_load_workspace(repo)
        assert tasks.get(again, task.id).title == "keep me"

    def test_a_legacy_workspace_is_upgraded_and_still_readable(self, tmp_path):
        from codeframe.core import tasks
        from codeframe.core.workspace import create_or_load_workspace, get_workspace

        repo = tmp_path / "repo"
        repo.mkdir()
        ws = create_or_load_workspace(repo)
        task = tasks.create(ws, title="survivor", description="d")
        _make_legacy(ws.db_path, ["batch_runs"])

        upgraded = get_workspace(repo)
        assert tasks.get(upgraded, task.id).title == "survivor"


class TestLegacyShapesTheTableDropTestCannotReach:
    """Dropping a whole table is too clean a simulation of "legacy".

    A dropped table comes back complete. Real legacy databases have tables that
    *exist* but are missing columns, or that hold data a newer index would
    reject. Sharing the DDL made ordering load-bearing: indexes must be created
    after the ALTER TABLE migrations that add their columns, and after the data
    fixups that make a UNIQUE index satisfiable.
    """

    def test_a_prds_table_without_chain_id_still_upgrades(self, tmp_path):
        """idx_prds_chain cannot be created before the column it indexes."""
        from codeframe.core.workspace import _ensure_schema_upgrades, _init_database

        db = tmp_path / "legacy.db"
        _init_database(db)
        conn = sqlite3.connect(db)
        conn.execute("DROP TABLE prds")
        conn.execute(
            "CREATE TABLE prds (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, "
            "title TEXT, content TEXT NOT NULL, metadata TEXT, "
            "created_at TEXT NOT NULL, version INTEGER DEFAULT 1, "
            "parent_id TEXT, change_summary TEXT)"
        )
        conn.execute("PRAGMA user_version = 0")
        conn.commit()
        conn.close()

        _ensure_schema_upgrades(db)  # must not raise "no such column: chain_id"

        conn = sqlite3.connect(db)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(prds)")}
            idx = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'")}
        finally:
            conn.close()
        assert {"chain_id", "depends_on"} <= cols
        assert "idx_prds_chain" in idx

    def test_duplicate_external_urls_are_deduped_before_the_unique_index(
        self, tmp_path
    ):
        """A UNIQUE index over dirty data must not brick the workspace."""
        from codeframe.core.workspace import _ensure_schema_upgrades, _init_database

        db = tmp_path / "dupes.db"
        _init_database(db)
        conn = sqlite3.connect(db)
        conn.execute("DROP INDEX IF EXISTS idx_tasks_external_url")
        for task_id in ("t1", "t2"):
            conn.execute(
                "INSERT INTO tasks (id, workspace_id, title, description, status, "
                "created_at, updated_at, external_url) "
                "VALUES (?, 'w1', 'T', 'd', 'BACKLOG', '2026-01-01', '2026-01-01', "
                "'https://github.com/o/r/issues/1')",
                (task_id,),
            )
        conn.execute("PRAGMA user_version = 0")
        conn.commit()
        conn.close()

        _ensure_schema_upgrades(db)  # must not raise IntegrityError

        conn = sqlite3.connect(db)
        try:
            urls = [r[0] for r in conn.execute(
                "SELECT external_url FROM tasks WHERE id IN ('t1','t2') ORDER BY id")]
            idx = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'")}
        finally:
            conn.close()
        assert urls[0] == "https://github.com/o/r/issues/1", "kept the oldest row"
        assert not urls[1], "the later duplicate should have been blanked"
        assert "idx_tasks_external_url" in idx

    def test_undedupable_duplicates_warn_instead_of_bricking(self, tmp_path, monkeypatch):
        """The #943 guard must survive being moved into the shared definition.

        Sharing the index DDL created a SECOND, unguarded attempt after the
        guarded one. If duplicates outlive the dedupe for any reason, that
        second attempt raises IntegrityError and the workspace never opens —
        reintroducing exactly what the guard exists to prevent.
        """
        from codeframe.core import workspace as ws

        db = tmp_path / "stuck.db"
        ws._init_database(db)
        conn = sqlite3.connect(db)
        conn.execute("DROP INDEX IF EXISTS idx_tasks_external_url")
        for task_id in ("t1", "t2"):
            conn.execute(
                "INSERT INTO tasks (id, workspace_id, title, description, status, "
                "created_at, updated_at, external_url) "
                "VALUES (?, 'w1', 'T', 'd', 'BACKLOG', '2026-01-01', '2026-01-01', "
                "'https://github.com/o/r/issues/1')",
                (task_id,),
            )
        conn.execute("PRAGMA user_version = 0")
        conn.commit()
        conn.close()

        # Dedupe cannot help — simulate it failing to clear the duplicates.
        monkeypatch.setattr(ws, "_dedupe_external_urls", lambda conn, cursor: None)

        ws._ensure_schema_upgrades(db)  # must not raise IntegrityError

        conn = sqlite3.connect(db)
        try:
            assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 2
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        finally:
            conn.close()
        assert version == ws.SCHEMA_VERSION, "the upgrade did not complete"

    def test_the_index_is_created_exactly_once_in_the_source(self):
        """Two attempts means one of them is unguarded — that was the bug."""
        source = Path("codeframe/core/workspace.py").read_text()
        assert source.count("CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_external_url") == 1

    def test_a_tasks_table_missing_columns_is_migrated_not_left_alone(self, tmp_path):
        """A legacy tasks table must come out fully migrated, whoever does it.

        Deliberately does not assert *which* code path adds the columns:
        `_create_core_tables` carries ALTER statements of its own, so the
        block in `_ensure_schema_upgrades` may well be redundant now (see the
        follow-up issue). What must not regress is the outcome — an old tasks
        table ends up with every current column.
        """
        from codeframe.core.workspace import _ensure_schema_upgrades, _init_database

        db = tmp_path / "legacy_tasks.db"
        _init_database(db)
        conn = sqlite3.connect(db)
        conn.execute("DROP TABLE tasks")
        conn.execute(
            "CREATE TABLE tasks (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, "
            "title TEXT NOT NULL, description TEXT, status TEXT NOT NULL, "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.execute("PRAGMA user_version = 0")
        conn.commit()
        conn.close()

        _ensure_schema_upgrades(db)

        conn = sqlite3.connect(db)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(tasks)")}
        finally:
            conn.close()
        assert {
            "depends_on", "parent_id", "requirement_ids",
            "github_issue_number", "external_url", "auto_close_github_issue",
        } <= cols, f"legacy tasks table was not migrated: {sorted(cols)}"
