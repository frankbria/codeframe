"""Tests for VerificationWrapper."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from codeframe.core.adapters.verification_wrapper import VerificationWrapper
from codeframe.core.adapters.agent_adapter import AgentAdapter, AgentEvent, AgentResult
from codeframe.core.gates import GateStatus


@pytest.fixture
def mock_workspace():
    ws = MagicMock()
    ws.repo_path = Path("/tmp/test-repo")
    return ws


@pytest.fixture
def mock_inner_adapter():
    adapter = MagicMock(spec=AgentAdapter)
    adapter.name = "mock"
    adapter.run.return_value = AgentResult(status="completed", output="done")
    return adapter


@pytest.fixture
def passing_gate_result():
    result = MagicMock()
    result.passed = True
    result.checks = []
    return result


@pytest.fixture
def failing_gate_result():
    check = MagicMock()
    check.name = "pytest"
    check.status = GateStatus.FAILED
    check.output = "FAILED test_main.py::test_foo - AssertionError"
    result = MagicMock()
    result.passed = False
    result.checks = [check]
    return result


class TestVerificationWrapper:
    def test_name_includes_inner(self, mock_inner_adapter, mock_workspace):
        wrapper = VerificationWrapper(mock_inner_adapter, mock_workspace)
        assert wrapper.name == "verified-mock"

    def test_passes_through_non_completed(self, mock_inner_adapter, mock_workspace):
        """If inner adapter fails/blocks, skip verification entirely."""
        mock_inner_adapter.run.return_value = AgentResult(
            status="failed", error="crash",
        )
        wrapper = VerificationWrapper(mock_inner_adapter, mock_workspace)
        result = wrapper.run("t1", "prompt", Path("/tmp"))
        assert result.status == "failed"

    def test_runs_gates_on_completed(
        self, mock_inner_adapter, mock_workspace, passing_gate_result,
    ):
        with patch(
            "codeframe.core.adapters.verification_wrapper.run_gates",
            return_value=passing_gate_result,
        ):
            wrapper = VerificationWrapper(mock_inner_adapter, mock_workspace)
            result = wrapper.run("t1", "prompt", Path("/tmp"))
            assert result.status == "completed"

    def test_self_correction_on_gate_failure(
        self,
        mock_inner_adapter,
        mock_workspace,
        failing_gate_result,
        passing_gate_result,
    ):
        """After gate failure, re-invoke adapter with error context, then pass."""
        with patch(
            "codeframe.core.adapters.verification_wrapper.run_gates",
        ) as mock_gates:
            # First call: gates fail. Second call (after correction): gates pass.
            mock_gates.side_effect = [failing_gate_result, passing_gate_result]

            wrapper = VerificationWrapper(
                mock_inner_adapter, mock_workspace, max_correction_rounds=3,
            )
            result = wrapper.run("t1", "prompt", Path("/tmp"))

            assert result.status == "completed"
            # Inner adapter called twice: initial + 1 correction
            assert mock_inner_adapter.run.call_count == 2
            # Second call should include error context in prompt
            second_prompt = mock_inner_adapter.run.call_args_list[1][0][1]
            assert "Verification Gate Failures" in second_prompt

    def test_exhausted_correction_rounds(
        self, mock_inner_adapter, mock_workspace, failing_gate_result,
    ):
        """If all correction rounds fail, return failed result."""
        with patch(
            "codeframe.core.adapters.verification_wrapper.run_gates",
            return_value=failing_gate_result,
        ):
            wrapper = VerificationWrapper(
                mock_inner_adapter, mock_workspace, max_correction_rounds=2,
            )
            result = wrapper.run("t1", "prompt", Path("/tmp"))

            assert result.status == "failed"
            assert "still failing after 2 correction rounds" in result.error

    def test_emits_verification_events(
        self, mock_inner_adapter, mock_workspace, passing_gate_result,
    ):
        events: list[AgentEvent] = []
        with patch(
            "codeframe.core.adapters.verification_wrapper.run_gates",
            return_value=passing_gate_result,
        ):
            wrapper = VerificationWrapper(mock_inner_adapter, mock_workspace)
            wrapper.run("t1", "prompt", Path("/tmp"), on_event=events.append)

            types = [e.type for e in events]
            assert "verification" in types
            assert "verification_passed" in types

    def test_correction_stops_on_inner_failure(
        self, mock_inner_adapter, mock_workspace, failing_gate_result,
    ):
        """If inner adapter fails during correction, stop immediately."""
        mock_inner_adapter.run.side_effect = [
            AgentResult(status="completed", output="v1"),
            AgentResult(status="failed", error="crash on retry"),
        ]
        with patch(
            "codeframe.core.adapters.verification_wrapper.run_gates",
            return_value=failing_gate_result,
        ):
            wrapper = VerificationWrapper(
                mock_inner_adapter, mock_workspace, max_correction_rounds=3,
            )
            result = wrapper.run("t1", "prompt", Path("/tmp"))
            assert result.status == "failed"
            assert result.error == "crash on retry"

    def test_conforms_to_agent_adapter_protocol(
        self, mock_inner_adapter, mock_workspace,
    ):
        wrapper = VerificationWrapper(mock_inner_adapter, mock_workspace)
        assert isinstance(wrapper, AgentAdapter)

    def test_format_gate_errors_with_output(self, failing_gate_result):
        summary = VerificationWrapper._format_gate_errors(failing_gate_result)
        assert "pytest" in summary
        assert "FAILED" in summary
        assert "test_main.py" in summary

    def test_format_gate_errors_no_failures(self, passing_gate_result):
        summary = VerificationWrapper._format_gate_errors(passing_gate_result)
        assert "no details available" in summary

    def test_custom_gate_names(
        self, mock_inner_adapter, mock_workspace, passing_gate_result,
    ):
        """Gate names are forwarded to run_gates."""
        with patch(
            "codeframe.core.adapters.verification_wrapper.run_gates",
            return_value=passing_gate_result,
        ) as mock_gates:
            wrapper = VerificationWrapper(
                mock_inner_adapter,
                mock_workspace,
                gate_names=["ruff"],
            )
            wrapper.run("t1", "prompt", Path("/tmp"))
            mock_gates.assert_called_once_with(
                mock_workspace, gates=["ruff"], verbose=False,
            )
