"""Tests for engine registry."""

import os

import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.v2

from codeframe.core.adapters.agent_adapter import AgentAdapter
from codeframe.core.engine_registry import (
    BUILTIN_ENGINES,
    EXTERNAL_ENGINES,
    VALID_ENGINES,
    get_adapter,
    get_builtin_adapter,
    get_external_adapter,
    is_external_engine,
    resolve_engine,
)


class TestResolveEngine:
    def test_cli_flag_wins(self):
        assert resolve_engine("claude-code") == "claude-code"

    def test_env_var_fallback(self):
        with patch.dict(os.environ, {"CODEFRAME_ENGINE": "opencode"}):
            assert resolve_engine(None) == "opencode"

    def test_default_is_react(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CODEFRAME_ENGINE", None)
            assert resolve_engine(None) == "react"

    def test_cli_overrides_env(self):
        with patch.dict(os.environ, {"CODEFRAME_ENGINE": "opencode"}):
            assert resolve_engine("plan") == "plan"

    def test_built_in_alias(self):
        assert resolve_engine("built-in") == "react"

    def test_invalid_engine_raises(self):
        with pytest.raises(ValueError, match="Invalid engine"):
            resolve_engine("nonexistent")

    def test_all_valid_engines_resolve(self):
        for engine in VALID_ENGINES:
            result = resolve_engine(engine)
            assert result in VALID_ENGINES


class TestIsExternalEngine:
    def test_claude_code_is_external(self):
        assert is_external_engine("claude-code") is True

    def test_opencode_is_external(self):
        assert is_external_engine("opencode") is True

    def test_kilocode_is_external(self):
        assert is_external_engine("kilocode") is True

    def test_react_is_not_external(self):
        assert is_external_engine("react") is False

    def test_plan_is_not_external(self):
        assert is_external_engine("plan") is False


class TestGetExternalAdapter:
    def test_claude_code_adapter(self):
        with patch("shutil.which", return_value="/usr/bin/claude"):
            adapter = get_external_adapter("claude-code")
            assert adapter.name == "claude-code"
            assert isinstance(adapter, AgentAdapter)

    def test_opencode_adapter(self):
        with patch("shutil.which", return_value="/usr/bin/opencode"):
            adapter = get_external_adapter("opencode")
            assert adapter.name == "opencode"
            assert isinstance(adapter, AgentAdapter)

    def test_kilocode_adapter(self):
        with patch("shutil.which", return_value="/usr/bin/kilo"):
            adapter = get_external_adapter("kilocode")
            assert adapter.name == "kilocode"
            assert isinstance(adapter, AgentAdapter)

    def test_invalid_engine_raises(self):
        with pytest.raises(ValueError, match="Unknown external engine"):
            get_external_adapter("react")

    def test_missing_binary_raises(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(EnvironmentError):
                get_external_adapter("claude-code")


class TestGetBuiltinAdapter:
    def test_react_adapter(self):
        ws = MagicMock()
        provider = MagicMock()
        adapter = get_builtin_adapter("react", ws, provider)
        assert adapter.name == "react"
        assert isinstance(adapter, AgentAdapter)

    def test_plan_adapter(self):
        ws = MagicMock()
        provider = MagicMock()
        adapter = get_builtin_adapter("plan", ws, provider)
        assert adapter.name == "plan"
        assert isinstance(adapter, AgentAdapter)

    def test_built_in_alias_maps_to_react(self):
        ws = MagicMock()
        provider = MagicMock()
        adapter = get_builtin_adapter("built-in", ws, provider)
        assert adapter.name == "react"

    def test_invalid_engine_raises(self):
        with pytest.raises(ValueError, match="Unknown builtin engine"):
            get_builtin_adapter("claude-code", MagicMock(), MagicMock())


class TestGetAdapter:
    def test_external_engine_no_workspace_needed(self):
        with patch("shutil.which", return_value="/usr/bin/claude"):
            adapter = get_adapter("claude-code")
            assert adapter.name == "claude-code"

    def test_builtin_requires_workspace(self):
        with pytest.raises(ValueError, match="requires workspace"):
            get_adapter("react")

    def test_builtin_with_workspace(self):
        ws = MagicMock()
        provider = MagicMock()
        adapter = get_adapter("react", workspace=ws, llm_provider=provider)
        assert adapter.name == "react"

    def test_passes_kwargs_to_external(self):
        with patch("shutil.which", return_value="/usr/bin/claude"):
            adapter = get_adapter("claude-code", allowlist=["Edit"])
            assert adapter.name == "claude-code"

    def test_passes_kwargs_to_builtin(self):
        ws = MagicMock()
        provider = MagicMock()
        adapter = get_adapter(
            "react", workspace=ws, llm_provider=provider, dry_run=True
        )
        assert adapter.name == "react"


class TestConstants:
    def test_external_and_builtin_cover_all_valid(self):
        """Every valid engine is either external or builtin."""
        assert VALID_ENGINES == EXTERNAL_ENGINES | BUILTIN_ENGINES

    def test_no_overlap(self):
        """External and builtin sets are disjoint."""
        assert EXTERNAL_ENGINES & BUILTIN_ENGINES == frozenset()
