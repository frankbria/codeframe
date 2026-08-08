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
