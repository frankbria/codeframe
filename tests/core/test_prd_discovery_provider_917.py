"""`get_active_session` must resolve the provider, not force Anthropic (#917).

`PrdDiscoverySession.__post_init__` was generalized in #861 to resolve through
`CODEFRAME_LLM_PROVIDER` -> `.codeframe/config.yaml` -> anthropic. But
`get_active_session` still read `ANTHROPIC_API_KEY` itself and passed it
explicitly, which takes the legacy branch and forces the Anthropic path.

The user-visible effect: a workspace configured for openai/ollama — a documented,
supported configuration — could *start* discovery but never *resume* it. `cf prd
generate` exited with "Set ANTHROPIC_API_KEY", and `POST /api/v2/discovery/start`
returned 500. Worse, if an Anthropic key happened to be present, resuming
silently switched provider mid-session.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path: Path):
    """A workspace with one in-progress discovery session on disk."""
    from codeframe.core.prd_discovery import _ensure_discovery_schema

    ws = MagicMock()
    ws.id = "ws-917"
    ws.repo_path = tmp_path
    db = tmp_path / "codeframe.db"
    ws.db_path = db

    _ensure_discovery_schema(ws)

    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        INSERT INTO discovery_sessions
            (id, workspace_id, state, qa_history, current_question, coverage,
             created_at, updated_at)
        VALUES (?, ?, 'discovering', '[]', 'What are you building?', '{}',
                datetime('now'), datetime('now'))
        """,
        ("sess-917", ws.id),
    )
    conn.commit()
    conn.close()
    return ws


def _clear_keys(monkeypatch) -> None:
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CODEFRAME_LLM_PROVIDER"):
        monkeypatch.delenv(key, raising=False)


class TestGetActiveSessionResolvesProvider:
    def test_resumes_with_openai_and_no_anthropic_key(self, workspace, monkeypatch) -> None:
        """The headline case: an OpenAI-configured workspace can resume (AC2)."""
        from codeframe.core import prd_discovery

        _clear_keys(monkeypatch)
        monkeypatch.setenv("CODEFRAME_LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")

        session = prd_discovery.get_active_session(workspace)

        assert session is not None, "an OpenAI workspace could not resume its session"
        assert session.session_id == "sess-917"

    def test_does_not_force_the_anthropic_provider(self, workspace, monkeypatch) -> None:
        """Resolution must run, rather than an explicit key short-circuiting it."""
        from codeframe.core import prd_discovery

        _clear_keys(monkeypatch)
        monkeypatch.setenv("CODEFRAME_LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")

        session = prd_discovery.get_active_session(workspace)

        assert session is not None
        assert session.api_key is None, (
            "an explicit api_key takes __post_init__'s legacy branch and forces "
            "AnthropicProvider regardless of the configured provider"
        )
        assert "anthropic" not in type(session._llm_provider).__name__.lower()

    def test_an_anthropic_key_present_does_not_hijack_an_openai_session(
        self, workspace, monkeypatch
    ) -> None:
        """The silent-provider-switch case.

        Previously the mere presence of ANTHROPIC_API_KEY was enough to resume a
        session on Anthropic even when the workspace was configured otherwise.
        """
        from codeframe.core import prd_discovery

        _clear_keys(monkeypatch)
        monkeypatch.setenv("CODEFRAME_LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-be-ignored")

        session = prd_discovery.get_active_session(workspace)

        assert session is not None
        assert "anthropic" not in type(session._llm_provider).__name__.lower()

    def test_a_local_provider_needs_no_key_at_all(self, workspace, monkeypatch) -> None:
        """Ollama has no required key — resuming must not demand one."""
        from codeframe.core import prd_discovery

        _clear_keys(monkeypatch)
        monkeypatch.setenv("CODEFRAME_LLM_PROVIDER", "ollama")

        session = prd_discovery.get_active_session(workspace)
        assert session is not None

    def test_the_error_names_the_resolved_providers_key(self, workspace, monkeypatch) -> None:
        """AC3: not 'Set ANTHROPIC_API_KEY' when the provider is OpenAI."""
        from codeframe.core import prd_discovery
        from codeframe.core.prd_discovery import NoApiKeyError

        _clear_keys(monkeypatch)
        monkeypatch.setenv("CODEFRAME_LLM_PROVIDER", "openai")

        with pytest.raises(NoApiKeyError) as excinfo:
            prd_discovery.get_active_session(workspace)

        message = str(excinfo.value)
        assert "OPENAI_API_KEY" in message
        assert "ANTHROPIC_API_KEY" not in message

    def test_anthropic_still_works_as_the_default(self, workspace, monkeypatch) -> None:
        """The default path must be untouched."""
        from codeframe.core import prd_discovery

        _clear_keys(monkeypatch)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

        session = prd_discovery.get_active_session(workspace)
        assert session is not None
        assert "anthropic" in type(session._llm_provider).__name__.lower()

    def test_no_active_session_returns_none(self, tmp_path, monkeypatch) -> None:
        """An empty workspace must not raise about keys before finding nothing."""
        from codeframe.core import prd_discovery
        from codeframe.core.prd_discovery import _ensure_discovery_schema

        _clear_keys(monkeypatch)
        ws = MagicMock()
        ws.id = "ws-empty"
        ws.repo_path = tmp_path
        ws.db_path = tmp_path / "codeframe.db"
        _ensure_discovery_schema(ws)

        assert prd_discovery.get_active_session(ws) is None


class TestApiRoutePath:
    def test_discovery_start_resumes_under_openai(self, workspace, monkeypatch) -> None:
        """The route delegates to get_active_session, so it inherits the fix (AC2)."""
        from codeframe.core import prd_discovery

        _clear_keys(monkeypatch)
        monkeypatch.setenv("CODEFRAME_LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")

        with patch.object(prd_discovery, "logger"):
            session = prd_discovery.get_active_session(workspace)

        assert session is not None and session.session_id == "sess-917"
