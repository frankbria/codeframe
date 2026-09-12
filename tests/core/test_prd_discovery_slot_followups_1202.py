"""Single-active-slot follow-ups from #1042 (#1202).

Three loose ends #1201 disclosed and left: resuming into a taken slot could
only fail, a reset landing between pause's two writes orphaned a blocker with
no way to unwind it, and the "active session" predicate was written by hand in
three places with nothing keeping them identical.
"""

import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codeframe.core import blockers
from codeframe.core.workspace import Workspace, create_or_load_workspace, get_db_connection

pytestmark = pytest.mark.v2


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


def _states(workspace: Workspace) -> dict[str, str]:
    conn = get_db_connection(workspace)
    rows = conn.execute("SELECT id, state FROM discovery_sessions").fetchall()
    conn.close()
    return dict(rows)


@patch("codeframe.core.prd_discovery.AnthropicProvider")
class TestResumeIntoATakenSlot:
    def _paused_then_taken(self, workspace: Workspace):
        from codeframe.core.prd_discovery import PrdDiscoverySession

        paused = PrdDiscoverySession(workspace, api_key="test-key")
        paused.start_discovery()
        blocker_id = paused.pause_discovery("stepping away")
        # A paused row still holds the slot; the holder can only start once
        # the paused one is out of the way — which is what a user who never
        # comes back looks like.
        conn = get_db_connection(workspace)
        conn.execute(
            "UPDATE discovery_sessions SET state = 'completed' WHERE id = ?",
            (paused.session_id,),
        )
        conn.commit()
        conn.close()
        holder = PrdDiscoverySession(workspace, api_key="test-key")
        holder.start_discovery()
        return paused.session_id, blocker_id, holder.session_id

    def test_refuses_by_default_and_names_the_way_out(self, mock_provider_class, workspace):
        from codeframe.core.prd_discovery import ActiveSessionExistsError, PrdDiscoverySession

        mock_provider_class.return_value = _provider_returning()
        paused_id, blocker_id, holder_id = self._paused_then_taken(workspace)

        with pytest.raises(ActiveSessionExistsError, match="evict"):
            PrdDiscoverySession(workspace, api_key="test-key").resume_discovery(blocker_id)

        states = _states(workspace)
        assert states[holder_id] != "completed", "a refused resume must not touch the holder"
        assert states[paused_id] == "completed"

    def test_evict_closes_the_holder_and_resumes(self, mock_provider_class, workspace):
        from codeframe.core.prd_discovery import PrdDiscoverySession

        mock_provider_class.return_value = _provider_returning()
        paused_id, blocker_id, holder_id = self._paused_then_taken(workspace)

        resumed = PrdDiscoverySession(workspace, api_key="test-key")
        resumed.resume_discovery(blocker_id, evict=True)

        states = _states(workspace)
        assert resumed.session_id == paused_id
        assert states[paused_id] == "discovering"
        assert states[holder_id] == "completed", "evict must close the holder, not error"

    def test_evict_without_a_holder_is_a_plain_resume(self, mock_provider_class, workspace):
        from codeframe.core.prd_discovery import PrdDiscoverySession

        mock_provider_class.return_value = _provider_returning()
        paused = PrdDiscoverySession(workspace, api_key="test-key")
        paused.start_discovery()
        blocker_id = paused.pause_discovery("stepping away")

        resumed = PrdDiscoverySession(workspace, api_key="test-key")
        resumed.resume_discovery(blocker_id, evict=True)

        assert _states(workspace) == {paused.session_id: "discovering"}


class TestBlockerDelete:
    def test_delete_removes_an_open_blocker(self, workspace):
        created = blockers.create(workspace, question="orphan?", task_id=None, created_by="system")

        blockers.delete(workspace, created.id)

        assert blockers.get(workspace, created.id) is None
        assert blockers.list_all(workspace) == []

    def test_delete_of_an_unknown_blocker_raises(self, workspace):
        with pytest.raises(ValueError, match="not found"):
            blockers.delete(workspace, "nope")


@patch("codeframe.core.prd_discovery.AnthropicProvider")
class TestPauseUnwindsTheBlockerWhenTheSecondWriteIsRefused:
    def test_a_reset_between_the_two_writes_leaves_no_blocker(
        self, mock_provider_class, workspace, monkeypatch
    ):
        """Pause writes `paused`, creates the blocker, writes `blocker_id`. A
        reset landing between the two writes refuses the second; the blocker
        it just created must not survive with nothing pointing at it."""
        from codeframe.core import prd_discovery
        from codeframe.core.prd_discovery import (
            PrdDiscoverySession,
            SessionResetError,
            reset_discovery,
        )

        mock_provider_class.return_value = _provider_returning()
        session = PrdDiscoverySession(workspace, api_key="test-key")
        session.start_discovery()

        real_create = blockers.create
        created: list[str] = []

        def create_then_reset(*args, **kwargs):
            blocker = real_create(*args, **kwargs)
            created.append(blocker.id)
            reset_discovery(workspace, session_id=session.session_id)  # lands in the window
            return blocker

        monkeypatch.setattr(prd_discovery.blockers, "create", create_then_reset)

        with pytest.raises(SessionResetError):
            session.pause_discovery("user interrupted")

        assert created, "the premise: a blocker was created before the refused write"
        assert blockers.get(workspace, created[0]) is None, "orphaned blocker survived"
        assert _states(workspace)[session.session_id] == "completed"


class TestActivePredicateIsWrittenOnce:
    def test_the_unique_index_is_built_from_the_shared_predicate(self, workspace):
        from codeframe.core.prd_discovery import ACTIVE_SLOT_PREDICATE, _ensure_discovery_schema

        _ensure_discovery_schema(workspace)
        conn = get_db_connection(workspace)
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
            ("idx_discovery_sessions_one_active",),
        ).fetchone()[0]
        conn.close()

        assert ACTIVE_SLOT_PREDICATE in sql

    def test_the_predicate_literal_appears_exactly_once_in_the_module(self):
        from codeframe.core import prd_discovery

        source = inspect.getsource(prd_discovery)
        # The definition of ACTIVE_SLOT_PREDICATE, and nowhere else by hand.
        assert source.count("COALESCE(is_complete, 0) = 0") == 1

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_get_active_session_prefers_the_slot_holder_over_a_newer_finished_row(
        self, mock_provider_class, workspace, monkeypatch
    ):
        """#1201 pinned that a finished row's `updated_at` is never later than
        the holder's. This pins the stronger property: even when it *is*, the
        slot holder is returned."""
        from codeframe.core.prd_discovery import PrdDiscoverySession, get_active_session

        mock_provider_class.return_value = _provider_returning()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        finished = PrdDiscoverySession(workspace, api_key="test-key")
        finished.start_discovery()
        conn = get_db_connection(workspace)
        conn.execute(
            "UPDATE discovery_sessions SET is_complete = 1 WHERE id = ?", (finished.session_id,)
        )
        conn.commit()
        conn.close()

        fresh = PrdDiscoverySession(workspace, api_key="test-key")
        fresh.start_discovery()

        conn = get_db_connection(workspace)
        conn.execute(
            "UPDATE discovery_sessions SET updated_at = '9999-01-01T00:00:00' WHERE id = ?",
            (finished.session_id,),
        )
        conn.commit()
        conn.close()

        active = get_active_session(workspace)
        assert active is not None
        assert active.session_id == fresh.session_id


def test_db_connections_use_implicit_transactions(workspace):
    """`_ensure_discovery_schema`'s backfill and its CREATE UNIQUE INDEX are
    atomic only because sqlite3's implicit transaction spans both statements.
    `isolation_level=None` (autocommit) would split them, and a concurrent
    INSERT could land between. Nothing else records that dependency."""
    conn = get_db_connection(workspace)
    try:
        assert conn.isolation_level is not None
    finally:
        conn.close()
