"""Regression tests for routing direct provider constructions through llm_resolution (#861).

Each test class covers one of the 4 sites identified in the issue:
- conductor.SupervisorResolver.llm
- dependency_analyzer.analyze_dependencies
- prd_discovery.PrdDiscoverySession
- streaming_chat.StreamingChatAdapter

Mirrors the pattern from ``tests/ui/test_discovery_generate_tasks.py`` (#768):
set ``CODEFRAME_LLM_PROVIDER=ollama``, delete ``ANTHROPIC_API_KEY``, mock
``create_provider``, and assert the chain is invoked + the resulting provider
is the one used downstream.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest

from codeframe.core.workspace import create_or_load_workspace


pytestmark = pytest.mark.v2


@pytest.fixture
def workspace():
    """Temporary workspace for tests that need one."""
    with TemporaryDirectory() as tmpdir:
        ws = create_or_load_workspace(Path(tmpdir))
        yield ws


@pytest.fixture
def ollama_env(monkeypatch):
    """Point the chain at ollama and clear the Anthropic key.

    With this env, any code path that still hardcodes AnthropicProvider will
    fail (no key); any code path that uses the chain resolves to ollama.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CODEFRAME_LLM_PROVIDER", "ollama")
    # Stub OPENAI_BASE_URL unset so the chain doesn't pick up unrelated state
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)


# ---------------------------------------------------------------------------
# Site 1: conductor.SupervisorResolver.llm
# ---------------------------------------------------------------------------


class TestSupervisorResolverProviderResolution:
    """SupervisorResolver.llm must resolve via the shared chain (#861)."""

    def test_llm_property_uses_chain(self, workspace, ollama_env):
        from codeframe.core.conductor import SupervisorResolver

        fake_provider = MagicMock(name="ollama-provider")
        with patch(
            "codeframe.core.llm_resolution.create_provider",
            return_value=fake_provider,
        ) as mock_create:
            supervisor = SupervisorResolver(workspace)
            llm = supervisor.llm  # triggers lazy init

        assert llm is fake_provider
        mock_create.assert_called_once()
        # The chain should have resolved to ollama (from CODEFRAME_LLM_PROVIDER)
        settings = mock_create.call_args.args[0]
        assert settings.provider_type == "ollama"

    def test_llm_property_caches_provider(self, workspace, ollama_env):
        """Lazy property must only construct once."""
        from codeframe.core.conductor import SupervisorResolver

        fake_provider = MagicMock(name="ollama-provider")
        with patch(
            "codeframe.core.llm_resolution.create_provider",
            return_value=fake_provider,
        ) as mock_create:
            supervisor = SupervisorResolver(workspace)
            _ = supervisor.llm
            _ = supervisor.llm  # second access

        mock_create.assert_called_once()


# ---------------------------------------------------------------------------
# Site 2: dependency_analyzer.analyze_dependencies
# ---------------------------------------------------------------------------


class TestDependencyAnalyzerProviderResolution:
    """analyze_dependencies(..., provider=None) must resolve via the chain (#861)."""

    def test_none_provider_uses_chain(self, workspace, ollama_env):
        from codeframe.adapters.llm.base import Purpose
        from codeframe.core import tasks as task_module
        from codeframe.core.dependency_analyzer import analyze_dependencies
        from codeframe.core.state_machine import TaskStatus

        # Seed one task so analyze_dependencies reaches the provider call
        task = task_module.create(
            workspace,
            title="Set up project structure",
            description="Initialize the repo",
            status=TaskStatus.READY,
        )

        fake_provider = MagicMock(name="ollama-provider")
        # Make complete() return a JSON response the parser accepts
        fake_provider.complete.return_value = MagicMock(content="{}")
        with patch(
            "codeframe.core.llm_resolution.create_provider",
            return_value=fake_provider,
        ) as mock_create:
            result = analyze_dependencies(workspace, [task.id], provider=None)

        # Parser returns {task_id: []} for the "{}" response — the point is
        # that the chain was used and the fake provider's .complete() ran.
        assert result == {task.id: []}
        mock_create.assert_called_once()
        settings = mock_create.call_args.args[0]
        assert settings.provider_type == "ollama"
        # And the fake provider is the one whose .complete() was called
        fake_provider.complete.assert_called_once()
        # Sanity: the purpose kwarg is threading through (PLANNING)
        _, kwargs = fake_provider.complete.call_args
        assert kwargs.get("purpose") == Purpose.PLANNING

    def test_explicit_provider_skips_chain(self, workspace, ollama_env):
        """Passing provider= must NOT trigger the chain."""
        from codeframe.core.dependency_analyzer import analyze_dependencies

        explicit_provider = MagicMock(name="explicit")
        explicit_provider.complete.return_value = MagicMock(content="{}")
        with patch(
            "codeframe.core.llm_resolution.create_provider"
        ) as mock_create:
            analyze_dependencies(workspace, [], provider=explicit_provider)
        mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# Site 3: prd_discovery.PrdDiscoverySession
# ---------------------------------------------------------------------------


class TestPrdDiscoveryProviderResolution:
    """PrdDiscoverySession without api_key must resolve via the chain (#861)."""

    def test_no_api_key_uses_chain(self, workspace, ollama_env):
        from codeframe.core.prd_discovery import PrdDiscoverySession

        fake_provider = MagicMock(name="ollama-provider")
        with patch(
            "codeframe.core.llm_resolution.create_provider",
            return_value=fake_provider,
        ) as mock_create:
            session = PrdDiscoverySession(workspace)  # no api_key

        assert session._llm_provider is fake_provider
        mock_create.assert_called_once()
        settings = mock_create.call_args.args[0]
        assert settings.provider_type == "ollama"

    def test_explicit_api_key_skips_chain(self, workspace, ollama_env):
        """Backward-compat: explicit api_key still constructs AnthropicProvider."""
        from codeframe.core.prd_discovery import PrdDiscoverySession

        with patch(
            "codeframe.core.llm_resolution.create_provider"
        ) as mock_create, patch(
            "codeframe.core.prd_discovery.AnthropicProvider"
        ) as mock_anthropic:
            PrdDiscoverySession(workspace, api_key="legacy-key")
        mock_create.assert_not_called()
        mock_anthropic.assert_called_once_with(api_key="legacy-key")

    def test_missing_required_key_still_raises(self, workspace, monkeypatch):
        """When the chain resolves to a keyed provider with no key, NoApiKeyError
        is still raised at construction — preserves the pre-migration contract."""
        from codeframe.core.prd_discovery import NoApiKeyError, PrdDiscoverySession

        # anthropic by default, no key anywhere
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("CODEFRAME_LLM_PROVIDER", raising=False)

        with pytest.raises(NoApiKeyError):
            PrdDiscoverySession(workspace)  # no api_key, no env


# ---------------------------------------------------------------------------
# Site 4: streaming_chat.StreamingChatAdapter
# ---------------------------------------------------------------------------


class TestStreamingChatProviderResolution:
    """StreamingChatAdapter with no provider must resolve via the chain (#861)."""

    def test_no_provider_uses_chain(self, ollama_env):
        from codeframe.core.adapters.streaming_chat import StreamingChatAdapter

        fake_provider = MagicMock(name="ollama-provider")
        with patch(
            "codeframe.core.llm_resolution.create_provider",
            return_value=fake_provider,
        ) as mock_create:
            adapter = StreamingChatAdapter(
                session_id="s1",
                db_repo=MagicMock(),
                workspace_path=Path("/tmp"),
            )

        assert adapter._provider is fake_provider
        mock_create.assert_called_once()
        settings = mock_create.call_args.args[0]
        assert settings.provider_type == "ollama"

    def test_explicit_provider_skips_chain(self, ollama_env):
        from codeframe.core.adapters.streaming_chat import StreamingChatAdapter

        explicit = MagicMock(name="explicit")
        with patch(
            "codeframe.core.llm_resolution.create_provider"
        ) as mock_create:
            adapter = StreamingChatAdapter(
                session_id="s1",
                db_repo=MagicMock(),
                workspace_path=Path("/tmp"),
                provider=explicit,
            )
        mock_create.assert_not_called()
        assert adapter._provider is explicit
