"""One function creates tables, one migrates columns (#1104).

`_create_core_tables` was extracted from `_init_database` in #1060 and brought
15 `ALTER TABLE` statements along with it — 12 on `tasks` that
`_ensure_schema_upgrades` already performs verbatim, plus one on `blockers`.
Because `_ensure_schema_upgrades` calls `_create_core_tables` first, its own
`tasks` block always found the columns already present and did nothing.

Duplicated migrations are not harmless: the next column added to one copy and
not the other drifts silently, which is the same hazard #1060 closed one level
up. These tests pin the split — CREATE-only in one place, ALTERs in the other —
so the duplication cannot come back.
"""

from __future__ import annotations

import ast
import inspect
import sqlite3
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

# The tasks columns that were duplicated across both paths.
DUPLICATED_TASK_COLUMNS = (
    "depends_on",
    "estimated_hours",
    "complexity_score",
    "uncertainty_level",
    "github_issue_number",
    "parent_id",
    "lineage",
    "is_leaf",
    "hierarchical_id",
    "requirement_ids",
    "external_url",
    "auto_close_github_issue",
)


class TestTheSplitIsHonest:
    def test_create_core_tables_carries_no_alters(self):
        """The name promises tables. It must not also migrate columns."""
        from codeframe.core.workspace import _create_core_tables

        # Every SQL literal in the body. The docstring talks *about* ALTER
        # TABLE and comments explain where the migrations went, so scanning
        # raw lines would flag prose; only executed statements count.
        func = ast.parse(
            textwrap.dedent(inspect.getsource(_create_core_tables))
        ).body[0]
        if ast.get_docstring(func) is not None:
            del func.body[0]
        statements = [
            node.value
            for node in ast.walk(func)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        offenders = [s for s in statements if "ALTER TABLE" in s]
        assert not offenders, (
            "_create_core_tables performs column migrations:\n"
            + "\n".join(offenders)
        )

    @pytest.mark.parametrize("column", DUPLICATED_TASK_COLUMNS)
    def test_each_tasks_alter_appears_once_in_the_source(self, column):
        """Two copies of a migration is how the two paths drift apart."""
        source = Path("codeframe/core/workspace.py").read_text()
        ddl = f"ALTER TABLE tasks ADD COLUMN {column}"
        assert source.count(ddl) == 1, (
            f"{ddl!r} appears {source.count(ddl)} times; it must appear exactly once"
        )


class TestNoOutcomeRegressed:
    """Whoever performs the migration, a legacy database must come out current."""

    def test_a_legacy_blockers_table_gains_created_by(self, tmp_path):
        """`blockers.created_by` was migrated ONLY inside `_create_core_tables`.

        Removing the ALTER without relocating it would leave every pre-#565
        workspace without the column — and `blockers.create()` writes it.
        """
        from codeframe.core.workspace import _ensure_schema_upgrades, _init_database

        db = tmp_path / "legacy_blockers.db"
        _init_database(db)
        conn = sqlite3.connect(db)
        conn.execute("DROP TABLE blockers")
        conn.execute(
            "CREATE TABLE blockers (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, "
            "task_id TEXT, question TEXT NOT NULL, answer TEXT, "
            "status TEXT NOT NULL DEFAULT 'OPEN', created_at TEXT NOT NULL, "
            "answered_at TEXT)"
        )
        conn.execute("PRAGMA user_version = 0")
        conn.commit()
        conn.close()

        _ensure_schema_upgrades(db)

        conn = sqlite3.connect(db)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(blockers)")}
        finally:
            conn.close()
        assert "created_by" in cols, f"legacy blockers table not migrated: {sorted(cols)}"

    def test_a_legacy_tasks_table_still_gains_every_column(self, tmp_path):
        """The #1103 outcome, restated against the columns this issue moved."""
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
        assert set(DUPLICATED_TASK_COLUMNS) <= cols, (
            f"legacy tasks table was not migrated: {sorted(cols)}"
        )
