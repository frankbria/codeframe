"""Low-severity PRD, discovery and template defects (issue #961).

Six defects:

1. ``create_new_version``'s error path ran a bare ``ROLLBACK``, which itself
   raises "cannot rollback - no transaction is active" and masks the original
   exception.
2. ``list_chains`` drops legacy PRDs with a NULL ``chain_id`` (SQL ``NULL =
   NULL`` never matches), and the migration backfill skipped any row that had a
   ``parent_id`` — so a legacy PRD vanished from the chain list with no error.
3. ``submit_answer`` on a completed/loaded session validated against a ``None``
   question.
4. ``reset_discovery`` without a ``session_id`` reset **every** non-completed
   session, contradicting its docstring and destroying work across unrelated
   PRDs.
5. ``apply_template`` silently dropped out-of-range dependency indices,
   producing a task graph that looks fine and executes in the wrong order.
6. ``cf prd stress-test`` had no error handling around its multi-call LLM run,
   so a provider failure surfaced as a traceback.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.v2


# ─────────────────────────────────────────────────────────────────────────────
# 1. The rollback must not mask the original exception
# ─────────────────────────────────────────────────────────────────────────────


class _FlakyCursor:
    """Cursor that fails the INSERT and then fails the ROLLBACK too."""

    def __init__(self, real, boom):
        self._real = real
        self._boom = boom

    def execute(self, sql, *args, **kwargs):
        head = sql.strip().upper()
        if head.startswith("INSERT"):
            raise self._boom
        if head.startswith("ROLLBACK"):
            raise sqlite3.OperationalError(
                "cannot rollback - no transaction is active"
            )
        return self._real.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


class _FlakyConnection:
    def __init__(self, real, boom):
        self._real = real
        self._boom = boom

    def cursor(self):
        return _FlakyCursor(self._real.cursor(), self._boom)

    def __getattr__(self, name):
        return getattr(self._real, name)


class TestRollbackDoesNotMask:
    """sqlite3.Cursor is a C type and cannot be patched, so wrap the
    connection the module hands out instead."""

    def _install(self, monkeypatch, boom, opened):
        from codeframe.core import prd

        real_conn = prd.get_db_connection

        def factory(workspace):
            real = real_conn(workspace)
            opened.append(real)
            return _FlakyConnection(real, boom)

        monkeypatch.setattr(prd, "get_db_connection", factory)

    def test_original_exception_propagates_when_rollback_fails(
        self, tmp_path, monkeypatch
    ):
        from codeframe.core import prd
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        root = prd.store(ws, content="# v1", title="P")

        boom = RuntimeError("disk exploded mid-transaction")
        self._install(monkeypatch, boom, [])

        with pytest.raises(RuntimeError) as excinfo:
            prd.create_new_version(ws, root.id, "# v2", "s")

        assert excinfo.value is boom, "the rollback failure masked the real error"

    def test_connection_is_closed_even_when_rollback_fails(
        self, tmp_path, monkeypatch
    ):
        from codeframe.core import prd
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        root = prd.store(ws, content="# v1", title="P")

        opened: list = []
        self._install(monkeypatch, RuntimeError("boom"), opened)

        with pytest.raises(RuntimeError):
            prd.create_new_version(ws, root.id, "# v2", "s")

        assert opened, "expected a connection to be opened"
        for conn in opened:
            with pytest.raises(sqlite3.ProgrammingError):
                conn.execute("SELECT 1")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Legacy PRDs with NULL chain_id stay visible
# ─────────────────────────────────────────────────────────────────────────────


class TestLegacyChainsAreVisible:
    def _null_out_chain_ids(self, ws):
        from codeframe.core.workspace import get_db_connection

        conn = get_db_connection(ws)
        try:
            conn.execute("UPDATE prds SET chain_id = NULL")
            conn.commit()
        finally:
            conn.close()

    def test_a_legacy_root_prd_is_listed(self, tmp_path):
        from codeframe.core import prd
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        root = prd.store(ws, content="# legacy", title="Legacy")
        self._null_out_chain_ids(ws)

        chains = prd.list_chains(ws)
        assert [c.id for c in chains] == [root.id], "legacy PRD vanished"

    def test_a_legacy_child_prd_is_listed(self, tmp_path):
        """The migration skipped rows WITH a parent_id — the harder case."""
        from codeframe.core import prd
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        root = prd.store(ws, content="# v1", title="Legacy")
        v2 = prd.create_new_version(ws, root.id, "# v2", "s")
        self._null_out_chain_ids(ws)

        chains = prd.list_chains(ws)
        # One chain, represented by its latest version.
        assert len(chains) == 1
        assert chains[0].id == v2.id

    def test_the_migration_backfills_rows_that_have_a_parent(self, tmp_path):
        from codeframe.core import prd
        from codeframe.core.workspace import create_or_load_workspace, get_db_connection

        ws = create_or_load_workspace(tmp_path)
        root = prd.store(ws, content="# v1", title="Legacy")
        v2 = prd.create_new_version(ws, root.id, "# v2", "s")
        self._null_out_chain_ids(ws)

        conn = get_db_connection(ws)
        try:
            conn.execute("PRAGMA user_version = 0")
            conn.commit()
        finally:
            conn.close()

        # Reopening runs the upgrade path.
        ws2 = create_or_load_workspace(tmp_path)
        conn = get_db_connection(ws2)
        try:
            rows = dict(
                conn.execute("SELECT id, chain_id FROM prds").fetchall()
            )
        finally:
            conn.close()

        assert rows[root.id] == root.id
        assert rows[v2.id] == root.id, "child was not backfilled to its root"

    def test_normal_chains_are_unaffected(self, tmp_path):
        from codeframe.core import prd
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        a = prd.store(ws, content="# a", title="A")
        prd.create_new_version(ws, a.id, "# a2", "s")
        b = prd.store(ws, content="# b", title="B")

        chains = prd.list_chains(ws)
        assert len(chains) == 2
        assert {c.chain_id for c in chains} == {a.id, b.id}


# ─────────────────────────────────────────────────────────────────────────────
# 3. submit_answer on a finished session
# ─────────────────────────────────────────────────────────────────────────────


class TestSubmitAnswerOnFinishedSession:
    def test_completed_session_raises_a_clear_domain_error(self, tmp_path):
        from codeframe.core.prd_discovery import DiscoveryError, PrdDiscoverySession
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        session = PrdDiscoverySession.__new__(PrdDiscoverySession)
        session.workspace = ws
        session.session_id = "s1"
        session._qa_history = []
        session._current_question = None
        session._is_complete = True

        with pytest.raises(DiscoveryError) as excinfo:
            session.submit_answer("an answer")

        assert "complete" in str(excinfo.value).lower()

    def test_missing_current_question_raises_rather_than_validating_none(
        self, tmp_path
    ):
        from codeframe.core.prd_discovery import DiscoveryError, PrdDiscoverySession
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        session = PrdDiscoverySession.__new__(PrdDiscoverySession)
        session.workspace = ws
        session.session_id = "s1"
        session._qa_history = []
        session._current_question = None
        session._is_complete = False

        called = []
        session._validate_answer = lambda q, a: called.append((q, a))

        with pytest.raises(DiscoveryError):
            session.submit_answer("an answer")

        assert called == [], "validated against a None question"

    def test_the_api_maps_it_to_409_not_500(self):
        """A new exception type makes every handler a caller to re-check.

        DiscoveryError is not ValidationError, so it fell through to the
        router's generic `except Exception` and returned 500 with a stack
        trace for what is a client-state conflict.
        """
        import inspect

        from codeframe.ui.routers import discovery_v2

        source = inspect.getsource(discovery_v2.submit_answer)
        assert "except DiscoveryError" in source
        # Ordering matters: ValidationError and NoApiKeyError subclass it, so
        # a DiscoveryError arm placed first would swallow both.
        assert source.index("except ValidationError") < source.index(
            "except DiscoveryError"
        )
        assert source.index("except NoApiKeyError") < source.index(
            "except DiscoveryError"
        )
        arm = source[source.index("except DiscoveryError"):]
        assert "409" in arm.split("except Exception")[0]

    def test_the_cli_handles_it_without_a_traceback(self):
        import inspect

        from codeframe.cli import app as cli_app

        source = inspect.getsource(cli_app.prd_generate)
        assert "except DiscoveryError" in source
        assert source.index("except ValidationError") < source.index(
            "except DiscoveryError"
        )

    def test_empty_answer_still_raises_validation_error(self, tmp_path):
        from codeframe.core.prd_discovery import PrdDiscoverySession, ValidationError
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        session = PrdDiscoverySession.__new__(PrdDiscoverySession)
        session.workspace = ws
        session.session_id = "s1"
        session._qa_history = []
        session._current_question = "What?"
        session._is_complete = False

        with pytest.raises(ValidationError):
            session.submit_answer("   ")


# ─────────────────────────────────────────────────────────────────────────────
# 4. reset_discovery scope
# ─────────────────────────────────────────────────────────────────────────────


class TestResetDiscoveryScope:
    def _make_sessions(self, ws, count):
        from codeframe.core.prd_discovery import _ensure_discovery_schema
        from codeframe.core.workspace import get_db_connection

        _ensure_discovery_schema(ws)
        conn = get_db_connection(ws)
        ids = []
        try:
            for i in range(count):
                sid = f"session-{i}"
                conn.execute(
                    "INSERT INTO discovery_sessions "
                    "(id, workspace_id, state, qa_history, created_at, updated_at) "
                    "VALUES (?, ?, 'discovering', '[]', ?, ?)",
                    (sid, ws.id, f"2026-01-0{i + 1}T00:00:00", f"2026-01-0{i + 1}T00:00:00"),
                )
                ids.append(sid)
            conn.commit()
        finally:
            conn.close()
        return ids

    def _states(self, ws):
        from codeframe.core.workspace import get_db_connection

        conn = get_db_connection(ws)
        try:
            return dict(
                conn.execute(
                    "SELECT id, state FROM discovery_sessions WHERE workspace_id = ?",
                    (ws.id,),
                ).fetchall()
            )
        finally:
            conn.close()

    def test_reset_without_id_touches_only_the_most_recent_session(self, tmp_path):
        from codeframe.core.prd_discovery import reset_discovery
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        ids = self._make_sessions(ws, 3)

        assert reset_discovery(ws) is True

        states = self._states(ws)
        assert states[ids[-1]] == "completed", "the active session was not reset"
        for older in ids[:-1]:
            assert states[older] == "discovering", (
                f"reset destroyed unrelated session {older}"
            )

    def test_reset_with_an_explicit_id_still_targets_that_session(self, tmp_path):
        from codeframe.core.prd_discovery import reset_discovery
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        ids = self._make_sessions(ws, 3)

        assert reset_discovery(ws, session_id=ids[0]) is True

        states = self._states(ws)
        assert states[ids[0]] == "completed"
        assert states[ids[1]] == "discovering"

    def test_reset_with_no_sessions_returns_false(self, tmp_path):
        from codeframe.core.prd_discovery import reset_discovery
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        assert reset_discovery(ws) is False


# ─────────────────────────────────────────────────────────────────────────────
# 5. apply_template rejects an out-of-range dependency index
# ─────────────────────────────────────────────────────────────────────────────


class TestTemplateDependencyIndices:
    def _patch_manager(self, task_dicts):
        """Patch the template manager to return exactly these task dicts."""
        from codeframe.core import templates

        class FakeManager:
            def get_template(self, template_id):
                return object()

            def apply_template(self, template_id, context, issue_number):
                return task_dicts

        return patch.object(templates, "TaskTemplateManager", lambda *a, **k: FakeManager())

    def test_out_of_range_index_raises(self, tmp_path):
        from codeframe.core import tasks, templates
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        dicts = [
            {"title": "A", "description": "", "depends_on_indices": []},
            {"title": "B", "description": "", "depends_on_indices": [5]},
        ]
        with self._patch_manager(dicts):
            with pytest.raises(ValueError) as excinfo:
                templates.apply_template(ws, "t1")

        assert "5" in str(excinfo.value)
        # Rejected before any task is created — no half-built graph left behind.
        assert tasks.list_tasks(ws) == []

    def test_negative_index_raises(self, tmp_path):
        from codeframe.core import templates
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        dicts = [{"title": "A", "description": "", "depends_on_indices": [-1]}]
        with self._patch_manager(dicts):
            with pytest.raises(ValueError):
                templates.apply_template(ws, "t1")

    def test_valid_indices_still_wire_up(self, tmp_path):
        from codeframe.core import tasks, templates
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        dicts = [
            {"title": "A", "description": "", "depends_on_indices": []},
            {"title": "B", "description": "", "depends_on_indices": [0]},
        ]
        with self._patch_manager(dicts):
            result = templates.apply_template(ws, "t1")

        assert result.tasks_created == 2
        b = tasks.get(ws, result.task_ids[1])
        assert b.depends_on == [result.task_ids[0]]


# ─────────────────────────────────────────────────────────────────────────────
# 6. The CLI surfaces provider failures
# ─────────────────────────────────────────────────────────────────────────────


class TestStressTestProviderErrors:
    def test_provider_failure_is_an_actionable_message_not_a_traceback(self, tmp_path):
        from typer.testing import CliRunner

        from codeframe.cli import app as cli_app
        from codeframe.core import prd
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        prd.store(ws, content="# PRD", title="P")

        with patch("codeframe.core.llm_resolution.create_provider"), \
             patch("codeframe.cli.validators.require_api_key_for_provider"), \
             patch(
                 "codeframe.core.prd_stress_test.stress_test_prd",
                 side_effect=RuntimeError("upstream 503 from provider"),
             ):
            result = CliRunner().invoke(
                cli_app.app,
                ["prd", "stress-test", "--workspace", str(tmp_path)],
            )

        assert result.exit_code == 1
        assert result.exception is None or isinstance(result.exception, SystemExit), (
            "provider failure escaped as a traceback"
        )
        assert "upstream 503 from provider" in " ".join(result.output.split())

    def test_refine_provider_failure_is_also_handled(self, tmp_path):
        from typer.testing import CliRunner

        from codeframe.cli import app as cli_app
        from codeframe.core import prd
        from codeframe.core.prd_stress_test import (
            Ambiguity,
            Classification,
            DecompositionNode,
            StressTestResult,
        )
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        record = prd.store(ws, content="# PRD", title="P")
        fake = StressTestResult(
            prd_title="P",
            tree=[
                DecompositionNode(
                    id="n1", title="G", description="d",
                    classification=Classification.ATOMIC,
                    children=[], lineage=[], depth=0,
                )
            ],
            ambiguities=[
                Ambiguity(
                    id="a1", source_node_title="N", label="L",
                    questions=["q?"], recommendation="",
                )
            ],
            tech_spec_markdown="# Spec",
            ambiguity_report="",
        )

        with patch("codeframe.core.llm_resolution.create_provider"), \
             patch("codeframe.cli.validators.require_api_key_for_provider"), \
             patch("codeframe.core.prd_stress_test.stress_test_prd", return_value=fake), \
             patch(
                 "codeframe.core.prd_stress_test.resolve_ambiguities_into_prd",
                 side_effect=RuntimeError("rate limited"),
             ):
            result = CliRunner().invoke(
                cli_app.app,
                ["prd", "stress-test", "--interactive", "--workspace", str(tmp_path)],
                input="my answer\n",
            )

        assert result.exit_code == 1
        assert "rate limited" in " ".join(result.output.split())
        # No phantom version from a failed refine.
        assert len(prd.get_versions(ws, record.id)) == 1
