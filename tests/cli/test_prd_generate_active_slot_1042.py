"""`cf prd generate` and the workspace's single active-session slot (#1042).

A workspace now holds at most one *active* discovery session, enforced by a
partial UNIQUE index. Two CLI consequences fall out of that:

1. Declining "Resume?" means abandoning the existing session, so the command
   must say so to the database — otherwise `start_discovery()` is refused.
2. A session whose Q&A is finished does NOT hold the slot. Resetting it would
   destroy a PRD the user can still generate, and it was never necessary.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core.workspace import Workspace, create_or_load_workspace, get_db_connection

pytestmark = pytest.mark.v2

runner = CliRunner()


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    return create_or_load_workspace(tmp_path)


def _provider() -> MagicMock:
    provider = MagicMock()

    def complete(messages, **_kwargs):
        content = messages[0]["content"] if messages else ""
        response = MagicMock()
        if "assess the current coverage" in content.lower():
            response.content = json.dumps(
                {"scores": {}, "average": 10, "ready_for_prd": False, "reasoning": "early"}
            )
        else:
            response.content = "What problem are you trying to solve?"
        response.input_tokens, response.output_tokens = 10, 5
        return response

    provider.complete.side_effect = complete
    return provider


def _seed_session(workspace: Workspace, answered: int, is_complete: int) -> str:
    """Persist a session row directly — the CLI only reads it back."""
    from codeframe.core.prd_discovery import _ensure_discovery_schema

    _ensure_discovery_schema(workspace)
    qa = json.dumps(
        [{"question": f"q{i}", "answer": f"a{i}", "timestamp": "2026-01-01"} for i in range(answered)]
    )
    conn = get_db_connection(workspace)
    conn.execute(
        "INSERT INTO discovery_sessions (id, workspace_id, state, qa_history,"
        " current_question, coverage, blocker_id, is_complete, created_at, updated_at)"
        " VALUES ('seeded', ?, 'discovering', ?, 'What next?', NULL, NULL, ?,"
        " '2026-01-01', '2026-01-01')",
        (workspace.id, qa, is_complete),
    )
    conn.commit()
    conn.close()
    return "seeded"


def _states(workspace: Workspace) -> dict[str, str]:
    conn = get_db_connection(workspace)
    try:
        return dict(conn.execute("SELECT id, state FROM discovery_sessions").fetchall())
    finally:
        conn.close()


@patch("codeframe.core.llm_resolution.create_provider")
class TestDecliningResume:
    def test_declining_abandons_the_old_session_and_starts_a_new_one(
        self, mock_create_provider, workspace: Workspace, monkeypatch
    ):
        mock_create_provider.return_value = _provider()
        monkeypatch.chdir(workspace.repo_path)
        seeded = _seed_session(workspace, answered=2, is_complete=0)

        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace.repo_path)],
            input="n\n/quit\ny\n",  # decline resume, then quit
            env={"ANTHROPIC_API_KEY": "test-key"},
        )

        states = _states(workspace)
        assert states[seeded] == "completed", (
            f"declining must abandon the old session; got {states} / {result.output}"
        )
        fresh = [sid for sid, state in states.items() if sid != seeded and state != "completed"]
        assert len(fresh) == 1, f"a new session should have started: {states}"

    def test_the_prompt_says_declining_is_destructive(
        self, mock_create_provider, workspace: Workspace, monkeypatch
    ):
        mock_create_provider.return_value = _provider()
        monkeypatch.chdir(workspace.repo_path)
        _seed_session(workspace, answered=2, is_complete=0)

        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace.repo_path)],
            input="n\n/quit\ny\n",
            env={"ANTHROPIC_API_KEY": "test-key"},
        )

        assert "abandons" in result.output, result.output


@patch("codeframe.core.llm_resolution.create_provider")
class TestFinishedSessionIsPreserved:
    def test_a_finished_qa_session_is_not_reset(
        self, mock_create_provider, workspace: Workspace, monkeypatch
    ):
        """It does not hold the slot, and its PRD can still be generated."""
        mock_create_provider.return_value = _provider()
        monkeypatch.chdir(workspace.repo_path)
        seeded = _seed_session(workspace, answered=4, is_complete=1)

        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace.repo_path)],
            input="n\n/quit\ny\n",
            env={"ANTHROPIC_API_KEY": "test-key"},
        )

        states = _states(workspace)
        assert states[seeded] == "discovering", (
            f"a finished-Q&A session must survive; got {states} / {result.output}"
        )


@patch("codeframe.core.llm_resolution.create_provider")
class TestResumeIntoATakenSlot:
    """#1202: `--resume` into a workspace whose slot is held refuses by
    default and names `--force`; `--force` evicts the holder and resumes."""

    def _pause_then_take(self, workspace: Workspace) -> tuple[str, str, str]:
        from codeframe.core.prd_discovery import PrdDiscoverySession

        with patch("codeframe.core.prd_discovery.AnthropicProvider") as cls:
            cls.return_value = _provider()
            paused = PrdDiscoverySession(workspace, api_key="test-key")
            paused.start_discovery()
            blocker_id = paused.pause_discovery("stepping away")
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

    def test_refused_resume_exits_1_and_names_force(
        self, mock_create_provider, workspace: Workspace, monkeypatch
    ):
        mock_create_provider.return_value = _provider()
        monkeypatch.chdir(workspace.repo_path)
        _paused, blocker_id, holder = self._pause_then_take(workspace)

        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace.repo_path), "--resume", blocker_id],
            env={"ANTHROPIC_API_KEY": "test-key"},
        )

        assert result.exit_code == 1, result.output
        assert "--force" in result.output, result.output
        assert _states(workspace)[holder] != "completed"

    def test_force_evicts_the_holder_and_resumes(
        self, mock_create_provider, workspace: Workspace, monkeypatch
    ):
        mock_create_provider.return_value = _provider()
        monkeypatch.chdir(workspace.repo_path)
        paused, blocker_id, holder = self._pause_then_take(workspace)

        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace.repo_path), "--resume", blocker_id, "--force"],
            input="/quit\ny\n",
            env={"ANTHROPIC_API_KEY": "test-key"},
        )

        states = _states(workspace)
        assert states[holder] == "completed", f"{states} / {result.output}"
        assert "Resuming" in result.output, result.output
