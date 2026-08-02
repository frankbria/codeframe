"""PRD discovery hardening (#928).

Two defects, both in the discovery happy path:

1. ``start_discovery`` persisted the session row *before* the first LLM call, so
   a rate-limit/auth failure left a ``state=discovering, current_question=NULL``
   row that permanently 400s ``POST /api/v2/discovery/start``.
2. ``_validate_answer`` only guarded ``JSONDecodeError``, so a valid-but-unexpected
   JSON shape (a list, a dict missing ``reason``) raised KeyError/TypeError out of
   ``submit_answer`` — a 500 in the router, a traceback in the CLI.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codeframe.core.workspace import Workspace, create_or_load_workspace, get_db_connection

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    return create_or_load_workspace(tmp_path)


def _provider_returning(*contents: str) -> MagicMock:
    """Mock provider whose completions return `contents` in order (last repeats)."""
    provider = MagicMock()
    queue = list(contents)

    def complete(*_args, **_kwargs):
        response = MagicMock()
        response.content = queue.pop(0) if len(queue) > 1 else queue[0]
        response.input_tokens = 10
        response.output_tokens = 5
        return response

    provider.complete.side_effect = complete
    return provider


class TestFailedFirstQuestionLeavesNoSession:
    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_llm_failure_persists_nothing(self, mock_provider_class, workspace: Workspace):
        """A failing opening-question call must not leave an active session behind."""
        from codeframe.core.prd_discovery import PrdDiscoverySession, get_active_session

        provider = MagicMock()
        provider.complete.side_effect = RuntimeError("429 rate limited")
        mock_provider_class.return_value = provider

        session = PrdDiscoverySession(workspace, api_key="test-key")
        with pytest.raises(RuntimeError):
            session.start_discovery()

        assert get_active_session(workspace) is None

        conn = get_db_connection(workspace)
        rows = conn.execute("SELECT id FROM discovery_sessions").fetchall()
        conn.close()
        assert rows == []

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_second_start_succeeds_after_failure(
        self, mock_provider_class, workspace: Workspace
    ):
        """The route's `already active` 400 must not fire after a failed start."""
        from codeframe.core.prd_discovery import PrdDiscoverySession, get_active_session

        failing = MagicMock()
        failing.complete.side_effect = RuntimeError("429 rate limited")
        mock_provider_class.return_value = failing

        with pytest.raises(RuntimeError):
            PrdDiscoverySession(workspace, api_key="test-key").start_discovery()

        # Retry with a healthy provider — this is what a second POST /start does.
        mock_provider_class.return_value = _provider_returning("What are you building?")
        retry = PrdDiscoverySession(workspace, api_key="test-key")
        assert get_active_session(workspace) is None  # no stale row blocking the retry
        retry.start_discovery()

        assert retry.get_current_question()["text"] == "What are you building?"
        conn = get_db_connection(workspace)
        rows = conn.execute("SELECT current_question FROM discovery_sessions").fetchall()
        conn.close()
        assert [r[0] for r in rows] == ["What are you building?"]

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_slot_is_claimed_during_the_opening_llm_call(
        self, mock_provider_class, workspace: Workspace
    ):
        """The row must exist *while* the (minutes-long) LLM call runs.

        Rolling the claim back on failure is only safe if it is taken up front —
        otherwise a concurrent POST /start sees an unclaimed workspace and opens a
        second active session.
        """
        from codeframe.core.prd_discovery import PrdDiscoverySession

        observed = {}

        def slow_opening_question(*_args, **_kwargs):
            # The same row get_active_session() selects on — queried directly so
            # the probe does not re-run provider resolution.
            conn = get_db_connection(workspace)
            observed["active_mid_call"] = conn.execute(
                "SELECT id FROM discovery_sessions "
                "WHERE workspace_id = ? AND state != 'completed'",
                (workspace.id,),
            ).fetchall()
            conn.close()
            response = MagicMock()
            response.content = "What are you building?"
            return response

        provider = MagicMock()
        provider.complete.side_effect = slow_opening_question
        mock_provider_class.return_value = provider

        PrdDiscoverySession(workspace, api_key="test-key").start_discovery()

        assert observed["active_mid_call"], (
            "workspace was unclaimed during the opening LLM call — a concurrent "
            "/start would have created a second active session"
        )


class TestValidationResponseNormalization:
    """_validate_answer must return {adequate, reason, follow_up} for any parse."""

    @pytest.mark.parametrize(
        "raw",
        [
            '["adequate", "reason"]',       # a list
            '{"adequate": false}',          # dict missing `reason`
            '{"reason": "vague"}',          # dict missing `adequate`
            '"just a sentence"',            # a bare JSON string
            "42",                           # a bare JSON number
            "not json at all",              # unparseable (pre-existing guard)
        ],
    )
    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_shape_is_always_normalized(
        self, mock_provider_class, workspace: Workspace, raw: str
    ):
        from codeframe.core.prd_discovery import PrdDiscoverySession

        mock_provider_class.return_value = _provider_returning(raw)
        session = PrdDiscoverySession(workspace, api_key="test-key")

        result = session._validate_answer("What are you building?", "A CLI tool.")

        assert set(result) == {"adequate", "reason", "follow_up"}
        assert isinstance(result["adequate"], bool)
        assert isinstance(result["reason"], str) and result["reason"]
        assert result["follow_up"] is None or isinstance(result["follow_up"], str)

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_stringified_false_is_not_treated_as_adequate(
        self, mock_provider_class, workspace: Workspace
    ):
        """`"adequate": "false"` is falsy intent — bool("false") would invert it."""
        from codeframe.core.prd_discovery import PrdDiscoverySession

        mock_provider_class.return_value = _provider_returning(
            '{"adequate": "false", "reason": "Too vague."}'
        )
        session = PrdDiscoverySession(workspace, api_key="test-key")

        result = session._validate_answer("Q?", "A")

        assert result["adequate"] is False
        assert result["reason"] == "Too vague."

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_submit_answer_survives_malformed_validation(
        self, mock_provider_class, workspace: Workspace
    ):
        """End-to-end: a non-dict reply must not raise out of submit_answer.

        Every downstream call (coverage assessment, next question) sees the same
        junk shape, so this also covers the coverage-parse path.
        """
        from codeframe.core.prd_discovery import PrdDiscoverySession

        mock_provider_class.return_value = _provider_returning(
            "What are you building?",  # opening question
            '["unexpected", "shape"]',  # everything after
        )
        session = PrdDiscoverySession(workspace, api_key="test-key")
        session.start_discovery()

        result = session.submit_answer("A task orchestrator for coding agents.")

        assert result["accepted"] is True
        assert session.answered_count == 1

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_inadequate_without_reason_still_reports_feedback(
        self, mock_provider_class, workspace: Workspace
    ):
        """submit_answer reads validation["reason"] unguarded — it must exist."""
        from codeframe.core.prd_discovery import PrdDiscoverySession

        mock_provider_class.return_value = _provider_returning(
            "What are you building?",
            '{"adequate": false}',
        )
        session = PrdDiscoverySession(workspace, api_key="test-key")
        session.start_discovery()

        result = session.submit_answer("Stuff.")

        assert result["accepted"] is False
        assert isinstance(result["feedback"], str) and result["feedback"]
        assert session.answered_count == 0
