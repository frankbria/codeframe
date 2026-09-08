"""Atomic single-active-session claim for PRD discovery (#1042).

``POST /api/v2/discovery/start`` enforced "one active session per workspace"
with a read-then-write and no uniqueness constraint behind it, so two concurrent
starts could each INSERT a ``discovering`` row and the loser became an orphan.
The same table also let ``POST /reset`` be undone: ``_save_session`` used
``INSERT OR REPLACE``, so the post-LLM save flipped a row a concurrent reset had
just completed back to ``discovering``.
"""

import sqlite3
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codeframe.core.workspace import Workspace, create_or_load_workspace, get_db_connection

pytestmark = pytest.mark.v2

ACTIVE_INDEX = "idx_discovery_sessions_one_active"


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    return create_or_load_workspace(tmp_path)


def _provider_returning(content: str = "What are you building?") -> MagicMock:
    provider = MagicMock()
    response = MagicMock()
    response.content = content
    response.input_tokens = 10
    response.output_tokens = 5
    provider.complete.return_value = response
    return provider


def _active_rows(workspace: Workspace) -> list[str]:
    conn = get_db_connection(workspace)
    rows = conn.execute(
        "SELECT id FROM discovery_sessions WHERE state != 'completed' AND is_complete = 0"
    ).fetchall()
    conn.close()
    return [row[0] for row in rows]


class TestConcurrentStartClaimsOneSlot:
    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_two_concurrent_starts_yield_one_active_session(
        self, mock_provider_class, workspace: Workspace
    ):
        """Both threads pass the read check; exactly one may keep the slot."""
        from codeframe.core.prd_discovery import ActiveSessionExistsError, PrdDiscoverySession

        mock_provider_class.return_value = _provider_returning()

        # Both threads sit here after reading the table and before writing,
        # which is precisely the window the read-then-write check leaves open.
        at_the_gate = threading.Barrier(2)
        errors: list[BaseException] = []
        started: list[str] = []

        def start():
            session = PrdDiscoverySession(workspace, api_key="test-key")
            at_the_gate.wait(timeout=10)
            try:
                session.start_discovery()
                started.append(session.session_id)
            except BaseException as exc:  # noqa: BLE001 - recorded and asserted below
                errors.append(exc)

        threads = [threading.Thread(target=start) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert len(started) == 1, f"expected one winner, got {started} / {errors}"
        assert len(errors) == 1
        assert isinstance(errors[0], ActiveSessionExistsError)
        assert _active_rows(workspace) == started

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_serial_second_start_raises_rather_than_orphaning(
        self, mock_provider_class, workspace: Workspace
    ):
        from codeframe.core.prd_discovery import ActiveSessionExistsError, PrdDiscoverySession

        mock_provider_class.return_value = _provider_returning()

        first = PrdDiscoverySession(workspace, api_key="test-key")
        first.start_discovery()

        second = PrdDiscoverySession(workspace, api_key="test-key")
        with pytest.raises(ActiveSessionExistsError):
            second.start_discovery()

        assert _active_rows(workspace) == [first.session_id]

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_finished_qa_session_still_allows_a_new_start(
        self, mock_provider_class, workspace: Workspace
    ):
        """A session with is_complete=1 awaiting PRD generation is not "active".

        The route's guard is ``not existing.is_complete()``, so this start has
        always been allowed — the uniqueness predicate must agree with it.
        """
        from codeframe.core.prd_discovery import PrdDiscoverySession

        mock_provider_class.return_value = _provider_returning()

        first = PrdDiscoverySession(workspace, api_key="test-key")
        first.start_discovery()

        conn = get_db_connection(workspace)
        conn.execute(
            "UPDATE discovery_sessions SET is_complete = 1 WHERE id = ?", (first.session_id,)
        )
        conn.commit()
        conn.close()

        second = PrdDiscoverySession(workspace, api_key="test-key")
        second.start_discovery()

        assert _active_rows(workspace) == [second.session_id]


class TestMigrationToleratesExistingDuplicates:
    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_stale_duplicates_are_reconciled_before_the_index_builds(
        self, mock_provider_class, workspace: Workspace, monkeypatch: pytest.MonkeyPatch
    ):
        """A pre-#1042 workspace can already hold several non-completed rows."""
        from codeframe.core.prd_discovery import _ensure_discovery_schema, get_active_session

        mock_provider_class.return_value = _provider_returning()
        # get_active_session() resolves a provider off the env (#917), not the
        # patched class.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        _ensure_discovery_schema(workspace)
        conn = get_db_connection(workspace)
        conn.execute(f"DROP INDEX IF EXISTS {ACTIVE_INDEX}")
        # created_at ordering is deliberately the REVERSE of updated_at ordering,
        # so a backfill that kept the newest by the wrong column would fail here.
        for suffix, created, updated in (
            ("old", "2022-01-01", "2020-01-01"),
            ("mid", "2021-01-01", "2021-01-01"),
            ("new", "2020-01-01", "2022-01-01"),
        ):
            conn.execute(
                """
                INSERT INTO discovery_sessions
                    (id, workspace_id, state, qa_history, current_question,
                     coverage, blocker_id, is_complete, created_at, updated_at)
                VALUES (?, ?, 'discovering', '[]', 'q?', NULL, NULL, 0, ?, ?)
                """,
                (f"session-{suffix}", workspace.id, created, updated),
            )
        conn.commit()
        conn.close()

        _ensure_discovery_schema(workspace)

        assert _active_rows(workspace) == ["session-new"]
        active = get_active_session(workspace)
        assert active is not None and active.session_id == "session-new"

        conn = get_db_connection(workspace)
        index = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (ACTIVE_INDEX,)
        ).fetchone()
        conn.close()
        assert index is not None, "unique index must exist after reconciliation"

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_reconciliation_keeps_one_active_row_per_workspace(
        self, mock_provider_class, tmp_path: Path, workspace: Workspace
    ):
        """Reconciliation partitions by workspace rather than reducing to one row."""
        from codeframe.core.prd_discovery import _ensure_discovery_schema

        mock_provider_class.return_value = _provider_returning()

        _ensure_discovery_schema(workspace)
        conn = get_db_connection(workspace)
        conn.execute(f"DROP INDEX IF EXISTS {ACTIVE_INDEX}")
        conn.execute(
            "INSERT INTO workspace (id, repo_path, tech_stack, created_at, updated_at) "
            "VALUES ('other-workspace', ?, NULL, '2020-01-01', '2020-01-01')",
            (str(tmp_path / "other"),),
        )
        for workspace_id in (workspace.id, "other-workspace"):
            for suffix, updated in (("old", "2020-01-01"), ("new", "2022-01-01")):
                conn.execute(
                    """
                    INSERT INTO discovery_sessions
                        (id, workspace_id, state, qa_history, current_question,
                         coverage, blocker_id, is_complete, created_at, updated_at)
                    VALUES (?, ?, 'discovering', '[]', 'q?', NULL, NULL, 0, ?, ?)
                    """,
                    (f"{workspace_id}-{suffix}", workspace_id, updated, updated),
                )
        conn.commit()
        conn.close()

        _ensure_discovery_schema(workspace)

        conn = get_db_connection(workspace)
        rows = conn.execute(
            "SELECT id FROM discovery_sessions "
            "WHERE state != 'completed' AND is_complete = 0 ORDER BY id"
        ).fetchall()
        conn.close()
        assert [row[0] for row in rows] == [
            f"{workspace.id}-new",
            "other-workspace-new",
        ]


class TestResetDuringInFlightStart:
    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_post_llm_save_does_not_resurrect_a_reset_session(
        self, mock_provider_class, workspace: Workspace
    ):
        """`/reset` lands while the opening-question call is still running."""
        from codeframe.core.prd_discovery import (
            PrdDiscoverySession,
            SessionResetError,
            get_active_session,
            reset_discovery,
        )

        provider = MagicMock()

        def complete(*_args, **_kwargs):
            reset_discovery(workspace)
            response = MagicMock()
            response.content = "What are you building?"
            response.input_tokens = 10
            response.output_tokens = 5
            return response

        provider.complete.side_effect = complete
        mock_provider_class.return_value = provider

        session = PrdDiscoverySession(workspace, api_key="test-key")
        with pytest.raises(SessionResetError):
            session.start_discovery()

        assert _active_rows(workspace) == []
        assert get_active_session(workspace) is None

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_a_fresh_start_succeeds_after_the_reset_race(
        self, mock_provider_class, workspace: Workspace
    ):
        from codeframe.core.prd_discovery import (
            PrdDiscoverySession,
            SessionResetError,
            reset_discovery,
        )

        provider = MagicMock()
        calls = {"n": 0}

        def complete(*_args, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                reset_discovery(workspace)
            response = MagicMock()
            response.content = "What are you building?"
            response.input_tokens = 10
            response.output_tokens = 5
            return response

        provider.complete.side_effect = complete
        mock_provider_class.return_value = provider

        with pytest.raises(SessionResetError):
            PrdDiscoverySession(workspace, api_key="test-key").start_discovery()

        retry = PrdDiscoverySession(workspace, api_key="test-key")
        retry.start_discovery()
        assert _active_rows(workspace) == [retry.session_id]


class TestUniqueIndexIsEnforcedInTheDatabase:
    def test_a_second_active_row_is_rejected_by_sqlite(self, workspace: Workspace):
        """The guarantee is the constraint, not the Python check around it."""
        from codeframe.core.prd_discovery import _ensure_discovery_schema

        _ensure_discovery_schema(workspace)

        conn = get_db_connection(workspace)
        insert = """
            INSERT INTO discovery_sessions
                (id, workspace_id, state, qa_history, current_question,
                 coverage, blocker_id, is_complete, created_at, updated_at)
            VALUES (?, ?, 'discovering', '[]', 'q?', NULL, NULL, 0,
                    '2026-01-01', '2026-01-01')
        """
        conn.execute(insert, ("first", workspace.id))
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(insert, ("second", workspace.id))
        conn.close()


class TestResumeIntoATakenSlot:
    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_resume_reports_the_conflict_rather_than_a_raw_sqlite_error(
        self, mock_provider_class, workspace: Workspace
    ):
        """resume_discovery flips a session back to `discovering`.

        If the workspace claimed its slot meanwhile, that write is refused —
        the caller should learn why, not read "UNIQUE constraint failed".
        """
        from codeframe.core.prd_discovery import (
            ActiveSessionExistsError,
            PrdDiscoverySession,
            SessionState,
        )

        mock_provider_class.return_value = _provider_returning()

        abandoned = PrdDiscoverySession(workspace, api_key="test-key")
        abandoned.start_discovery()
        abandoned.state = SessionState.COMPLETED
        abandoned._save_session()

        holder = PrdDiscoverySession(workspace, api_key="test-key")
        holder.start_discovery()

        abandoned.state = SessionState.DISCOVERING
        with pytest.raises(ActiveSessionExistsError):
            abandoned._save_session()

        assert _active_rows(workspace) == [holder.session_id]


class TestSubmitAnswerHasTheSameWindow:
    """`submit_answer` validates against state read before a multi-second LLM
    call, so a `/reset` can land in between — exactly the `/start` window."""

    def _session_with(self, workspace: Workspace, provider: MagicMock):
        from codeframe.core.prd_discovery import PrdDiscoverySession

        with patch(
            "codeframe.core.prd_discovery.AnthropicProvider", return_value=_provider_returning()
        ):
            session = PrdDiscoverySession(workspace, api_key="test-key")
            session.start_discovery()
        session._llm_provider = provider
        return session

    def _answer_provider(self, workspace: Workspace, on_first_call) -> MagicMock:
        """Adequate-answer validation, then a next question; hook the first call."""
        provider = MagicMock()
        replies = ['{"adequate": true, "reason": "ok"}', "What else?"]
        calls = {"n": 0}

        def complete(*_args, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                on_first_call()
            response = MagicMock()
            response.content = replies[min(calls["n"] - 1, len(replies) - 1)]
            response.input_tokens, response.output_tokens = 10, 5
            return response

        provider.complete.side_effect = complete
        return provider

    def test_reset_during_answer_is_not_undone(self, workspace: Workspace):
        from codeframe.core.prd_discovery import (
            SessionResetError,
            get_active_session,
            reset_discovery,
        )

        session = self._session_with(
            workspace, self._answer_provider(workspace, lambda: reset_discovery(workspace))
        )

        with pytest.raises(SessionResetError):
            session.submit_answer("A todo app for teams, offline-first.")

        assert _active_rows(workspace) == []
        assert get_active_session(workspace) is None

    def test_a_competing_session_does_not_produce_a_raw_sql_error(
        self, workspace: Workspace
    ):
        """The regression this guards: an unguarded UPDATE moves the reset row
        back into the index's active set, and the route reports the SQL text."""
        from codeframe.core.prd_discovery import (
            PrdDiscoverySession,
            SessionResetError,
            reset_discovery,
        )

        def reset_then_start_a_new_one():
            reset_discovery(workspace)
            with patch(
                "codeframe.core.prd_discovery.AnthropicProvider",
                return_value=_provider_returning(),
            ):
                PrdDiscoverySession(workspace, api_key="test-key").start_discovery()

        session = self._session_with(
            workspace, self._answer_provider(workspace, reset_then_start_a_new_one)
        )

        with pytest.raises(SessionResetError):
            session.submit_answer("A todo app for teams, offline-first.")

        assert len(_active_rows(workspace)) == 1


class TestPauseDoesNotOrphanABlocker:
    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_a_refused_pause_creates_no_blocker(
        self, mock_provider_class, workspace: Workspace
    ):
        """The state write must come first: a blocker created before a write
        that gets refused is orphaned, and its resume hint never reaches anyone."""
        from codeframe.core import blockers
        from codeframe.core.prd_discovery import (
            PrdDiscoverySession,
            SessionResetError,
            reset_discovery,
        )

        mock_provider_class.return_value = _provider_returning()

        stale = PrdDiscoverySession(workspace, api_key="test-key")
        stale.start_discovery()

        # The slot changes hands while `stale` is still held in memory.
        reset_discovery(workspace, session_id=stale.session_id)
        holder = PrdDiscoverySession(workspace, api_key="test-key")
        holder.start_discovery()

        before = len(blockers.list_all(workspace))
        with pytest.raises(SessionResetError):
            stale.pause_discovery("user interrupted")

        assert len(blockers.list_all(workspace)) == before, "orphaned blocker created"
        assert _active_rows(workspace) == [holder.session_id]


class TestMigrationSurvivesLegacyRows:
    def _seed(self, workspace: Workspace, rows):
        conn = get_db_connection(workspace)
        conn.execute(f"DROP INDEX IF EXISTS {ACTIVE_INDEX}")
        for session_id, is_complete, updated in rows:
            conn.execute(
                """
                INSERT INTO discovery_sessions
                    (id, workspace_id, state, qa_history, current_question,
                     coverage, blocker_id, is_complete, created_at, updated_at)
                VALUES (?, ?, 'discovering', '[]', 'q?', NULL, NULL, ?, ?, ?)
                """,
                (session_id, workspace.id, is_complete, updated, updated),
            )
        conn.commit()
        conn.close()

    def test_a_null_is_complete_row_is_reconciled_not_skipped(self, workspace: Workspace):
        """`is_complete = 0` is *unknown* for NULL, so a bare `= 0` predicate
        leaves a legacy row outside both the backfill and the index."""
        from codeframe.core.prd_discovery import _ensure_discovery_schema

        _ensure_discovery_schema(workspace)
        self._seed(workspace, [("legacy", None, "2020-01-01"), ("live", 0, "2022-01-01")])

        _ensure_discovery_schema(workspace)

        conn = get_db_connection(workspace)
        active = conn.execute(
            "SELECT id FROM discovery_sessions "
            "WHERE state != 'completed' AND COALESCE(is_complete, 0) = 0"
        ).fetchall()
        conn.close()
        assert [row[0] for row in active] == ["live"]

    def test_a_null_id_row_does_not_brick_discovery(
        self, workspace: Workspace, monkeypatch: pytest.MonkeyPatch
    ):
        """SQLite permits NULL in a TEXT PRIMARY KEY, and one NULL makes
        `id NOT IN (...)` NULL for every row — the backfill would no-op and the
        index build would then fail on every discovery call, forever."""
        from codeframe.core.prd_discovery import _ensure_discovery_schema, get_active_session

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")  # get_active_session (#917)

        _ensure_discovery_schema(workspace)
        conn = get_db_connection(workspace)
        conn.execute(f"DROP INDEX IF EXISTS {ACTIVE_INDEX}")
        conn.execute(
            "INSERT INTO discovery_sessions (id, workspace_id, state, qa_history,"
            " current_question, coverage, blocker_id, is_complete, created_at, updated_at)"
            " VALUES (NULL, ?, 'discovering', '[]', 'q?', NULL, NULL, 0,"
            " '2020-01-01', '2020-01-01')",
            (workspace.id,),
        )
        conn.commit()
        conn.close()
        self._seed(workspace, [("live", 0, "2022-01-01")])

        _ensure_discovery_schema(workspace)  # must not raise

        conn = get_db_connection(workspace)
        index = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (ACTIVE_INDEX,)
        ).fetchone()
        conn.close()
        assert index is not None, "index must still build over a NULL-id row"
        assert get_active_session(workspace) is not None, "discovery must still work"

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_pause_does_not_resurrect_a_reset_session(
        self, mock_provider_class, workspace: Workspace
    ):
        """The unique index only fires once a *replacement* holds the slot.

        With no replacement, an unconditional pause write matches the completed
        row and flips it back to `paused` — undoing the reset and leaving the
        abandoned session active again.
        """
        from codeframe.core import blockers
        from codeframe.core.prd_discovery import (
            PrdDiscoverySession,
            SessionResetError,
            get_active_session,
            reset_discovery,
        )

        mock_provider_class.return_value = _provider_returning()

        session = PrdDiscoverySession(workspace, api_key="test-key")
        session.start_discovery()
        reset_discovery(workspace, session_id=session.session_id)

        before = len(blockers.list_all(workspace))
        with pytest.raises(SessionResetError):
            session.pause_discovery("user interrupted")

        assert _active_rows(workspace) == []
        assert get_active_session(workspace) is None
        assert len(blockers.list_all(workspace)) == before
