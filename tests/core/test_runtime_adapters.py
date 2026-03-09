"""Tests for runtime execute_agent with external engine adapters."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from codeframe.core.adapters.agent_adapter import AgentResult


@pytest.fixture
def mock_workspace(tmp_path):
    """Create a minimal workspace for testing."""
    ws = MagicMock()
    ws.repo_path = tmp_path
    ws.state_dir = tmp_path / ".codeframe"
    ws.state_dir.mkdir()
    ws.id = "test-ws"
    ws.tech_stack = None
    ws.db_path = str(tmp_path / "test.db")
    return ws


@pytest.fixture
def mock_run():
    """Create a minimal run record."""
    run = MagicMock()
    run.id = "run-1"
    run.task_id = "task-1"
    return run


def _runtime_patches():
    """Common patches for runtime tests that touch the database/filesystem."""
    return [
        patch("codeframe.core.runtime.get_db_connection"),
        patch("codeframe.core.runtime.events"),
        patch("codeframe.core.diagnostics.get_db_connection"),
        patch("codeframe.core.streaming.RunOutputLogger"),
    ]


class TestExecuteAgentExternalEngine:
    """Tests for external engine path in execute_agent."""

    def test_invalid_engine_raises(self, mock_workspace, mock_run):
        from codeframe.core.runtime import execute_agent

        with pytest.raises(ValueError, match="Invalid engine"):
            execute_agent(mock_workspace, mock_run, engine="nonexistent")

    def test_external_engine_skips_api_key_check(self, mock_workspace, mock_run):
        """External engines should not require ANTHROPIC_API_KEY."""
        from codeframe.core.runtime import execute_agent

        patches = _runtime_patches() + [
            patch(
                "codeframe.core.runtime.get_external_adapter",
                create=True,
            ),
            patch("codeframe.core.context_packager.ContextLoader"),
            patch("codeframe.core.runtime.complete_run"),
            patch("codeframe.core.adapters.verification_wrapper.run_gates"),
        ]

        with patch.dict("os.environ", {}, clear=True):
            import os
            os.environ.pop("ANTHROPIC_API_KEY", None)

            # Apply all patches
            mocks = {}
            for p in patches:
                m = p.start()
                mocks[p.attribute or ""] = m

            try:
                # Set up context loader mock
                mock_context = MagicMock()
                mock_context.to_prompt_context.return_value = "test context"
                from codeframe.core.context_packager import TaskContextPackager
                with patch.object(
                    TaskContextPackager, "build"
                ) as mock_build:
                    from codeframe.core.context_packager import PackagedContext
                    mock_build.return_value = PackagedContext(
                        prompt="test prompt", context=mock_context
                    )

                    # Mock the adapter returned by get_external_adapter
                    mock_adapter = MagicMock()
                    mock_adapter.name = "claude-code"
                    mock_adapter.run.return_value = AgentResult(
                        status="completed", output="done"
                    )

                    # Patch at the point of import inside runtime
                    with patch(
                        "codeframe.core.engine_registry.get_external_adapter",
                        return_value=mock_adapter,
                    ):
                        # Mock gate passing
                        with patch(
                            "codeframe.core.adapters.verification_wrapper.run_gates"
                        ) as mock_gates:
                            mock_gate_result = MagicMock()
                            mock_gate_result.passed = True
                            mock_gates.return_value = mock_gate_result

                            result = execute_agent(
                                mock_workspace,
                                mock_run,
                                engine="claude-code",
                            )
                            assert result.status.value == "completed"
            finally:
                for p in patches:
                    p.stop()

    def test_builtin_engine_still_requires_api_key(
        self, mock_workspace, mock_run
    ):
        """Builtin engines should still require ANTHROPIC_API_KEY."""
        from codeframe.core.runtime import execute_agent

        with patch.dict("os.environ", {}, clear=True):
            import os
            os.environ.pop("ANTHROPIC_API_KEY", None)

            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                execute_agent(mock_workspace, mock_run, engine="react")

    def test_valid_engines_include_external(self):
        """VALID_ENGINES should include external engine names."""
        from codeframe.core.engine_registry import VALID_ENGINES

        assert "claude-code" in VALID_ENGINES
        assert "opencode" in VALID_ENGINES
        assert "react" in VALID_ENGINES
        assert "plan" in VALID_ENGINES
        assert "built-in" in VALID_ENGINES
