"""Tests for VerificationWrapper."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from codeframe.core.adapters.verification_wrapper import (
    VerificationWrapper,
    build_escalation_question,
)
from codeframe.core.adapters.agent_adapter import AgentAdapter, AgentEvent, AgentResult
from codeframe.core.fix_tracker import FixAttemptTracker
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
    result.get_error_summary.return_value = "test_main.py:1:1: E001 test failure"
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

    def test_exhausted_correction_rounds_creates_blocker(
        self, mock_inner_adapter, mock_workspace, failing_gate_result,
    ):
        """If all correction rounds fail, create blocker and return blocked."""
        with (
            patch(
                "codeframe.core.adapters.verification_wrapper.run_gates",
                return_value=failing_gate_result,
            ),
            patch(
                "codeframe.core.adapters.verification_wrapper.blockers",
            ) as mock_blockers,
        ):
            mock_blocker = MagicMock()
            mock_blocker.id = "b-exhaust"
            mock_blockers.create.return_value = mock_blocker

            wrapper = VerificationWrapper(
                mock_inner_adapter, mock_workspace, max_correction_rounds=2,
            )
            result = wrapper.run("t1", "prompt", Path("/tmp"))

            assert result.status == "blocked"
            assert "still failing after 2 correction rounds" in result.error
            mock_blockers.create.assert_called_once()

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


class TestQuickFixIntegration:
    """Tests for quick fix integration in VerificationWrapper."""

    def test_quick_fix_applied_before_adapter_reinvocation(
        self, mock_inner_adapter, mock_workspace, failing_gate_result, passing_gate_result,
    ):
        """Quick fix should be tried before re-invoking the adapter."""
        with (
            patch(
                "codeframe.core.adapters.verification_wrapper.run_gates",
            ) as mock_gates,
            patch(
                "codeframe.core.adapters.verification_wrapper.find_quick_fix",
            ) as mock_find,
            patch(
                "codeframe.core.adapters.verification_wrapper.apply_quick_fix",
                return_value=(True, "Fixed"),
            ),
        ):
            # First gate check fails, quick fix applied, second gate check passes
            mock_gates.side_effect = [failing_gate_result, passing_gate_result]
            mock_find.return_value = MagicMock()  # Non-None = fix found

            wrapper = VerificationWrapper(
                mock_inner_adapter, mock_workspace, max_correction_rounds=3,
            )
            result = wrapper.run("t1", "prompt", Path("/tmp"))

            assert result.status == "completed"
            # Adapter should NOT be re-invoked — quick fix handled it
            assert mock_inner_adapter.run.call_count == 1

    def test_quick_fix_failure_falls_through_to_adapter(
        self, mock_inner_adapter, mock_workspace, failing_gate_result, passing_gate_result,
    ):
        """When quick fix fails, fall through to adapter re-invocation."""
        with (
            patch(
                "codeframe.core.adapters.verification_wrapper.run_gates",
            ) as mock_gates,
            patch(
                "codeframe.core.adapters.verification_wrapper.find_quick_fix",
                return_value=None,
            ),
        ):
            mock_gates.side_effect = [failing_gate_result, passing_gate_result]

            wrapper = VerificationWrapper(
                mock_inner_adapter, mock_workspace, max_correction_rounds=3,
            )
            result = wrapper.run("t1", "prompt", Path("/tmp"))

            assert result.status == "completed"
            # No quick fix found, so adapter re-invoked
            assert mock_inner_adapter.run.call_count == 2

    def test_quick_fix_apply_failure_falls_through(
        self, mock_inner_adapter, mock_workspace, failing_gate_result, passing_gate_result,
    ):
        """When quick fix is found but apply fails, fall through to adapter."""
        with (
            patch(
                "codeframe.core.adapters.verification_wrapper.run_gates",
            ) as mock_gates,
            patch(
                "codeframe.core.adapters.verification_wrapper.find_quick_fix",
            ) as mock_find,
            patch(
                "codeframe.core.adapters.verification_wrapper.apply_quick_fix",
                return_value=(False, "apply failed"),
            ),
        ):
            mock_gates.side_effect = [failing_gate_result, passing_gate_result]
            mock_find.return_value = MagicMock()

            wrapper = VerificationWrapper(
                mock_inner_adapter, mock_workspace, max_correction_rounds=3,
            )
            result = wrapper.run("t1", "prompt", Path("/tmp"))

            assert result.status == "completed"
            # Quick fix apply failed, so adapter re-invoked
            assert mock_inner_adapter.run.call_count == 2


class TestFixTrackerIntegration:
    """Tests for FixAttemptTracker integration in VerificationWrapper."""

    def test_fix_tracker_records_gate_failures(
        self, mock_inner_adapter, mock_workspace, failing_gate_result,
    ):
        """Gate failures should be recorded in the fix tracker."""
        failing_gate_result.get_error_summary = MagicMock(
            return_value="test.py:1:1: E501 Line too long"
        )
        with (
            patch(
                "codeframe.core.adapters.verification_wrapper.run_gates",
                return_value=failing_gate_result,
            ),
            patch(
                "codeframe.core.adapters.verification_wrapper.find_quick_fix",
                return_value=None,
            ),
        ):
            wrapper = VerificationWrapper(
                mock_inner_adapter, mock_workspace, max_correction_rounds=1,
            )
            wrapper.run("t1", "prompt", Path("/tmp"))

            assert wrapper.fix_tracker.get_total_failures() > 0


class TestEscalationIntegration:
    """Tests for escalation blocker creation in VerificationWrapper."""

    def test_escalation_creates_blocker_and_returns_blocked(
        self, mock_inner_adapter, mock_workspace, failing_gate_result,
    ):
        """When fix tracker recommends escalation, create blocker and return blocked."""
        failing_gate_result.get_error_summary = MagicMock(
            return_value="SyntaxError: invalid syntax"
        )
        with (
            patch(
                "codeframe.core.adapters.verification_wrapper.run_gates",
                return_value=failing_gate_result,
            ),
            patch(
                "codeframe.core.adapters.verification_wrapper.find_quick_fix",
                return_value=None,
            ),
            patch(
                "codeframe.core.adapters.verification_wrapper.blockers",
            ) as mock_blockers,
        ):
            mock_blocker = MagicMock()
            mock_blocker.id = "blocker-123"
            mock_blockers.create.return_value = mock_blocker

            # Use high max_correction_rounds but force escalation via tracker
            wrapper = VerificationWrapper(
                mock_inner_adapter, mock_workspace, max_correction_rounds=10,
            )
            # Pre-fill tracker to trigger escalation (3+ same-error failures)
            error_text = "SyntaxError: invalid syntax"
            for _ in range(4):
                wrapper.fix_tracker.record_attempt(error_text, "gate_failure")
                wrapper.fix_tracker.record_outcome(
                    error_text, "gate_failure",
                    __import__("codeframe.core.fix_tracker", fromlist=["FixOutcome"]).FixOutcome.FAILED,
                )

            result = wrapper.run("t1", "prompt", Path("/tmp"))

            assert result.status == "blocked"
            assert result.blocker_question is not None
            assert "escalation" in result.blocker_question.lower() or "failing" in result.blocker_question.lower()
            mock_blockers.create.assert_called_once()

    def test_max_retries_exhausted_creates_blocker(
        self, mock_inner_adapter, mock_workspace, failing_gate_result,
    ):
        """When all correction rounds exhausted, create blocker instead of returning failed."""
        failing_gate_result.get_error_summary = MagicMock(
            return_value="FAILED test_main.py::test_foo"
        )
        with (
            patch(
                "codeframe.core.adapters.verification_wrapper.run_gates",
                return_value=failing_gate_result,
            ),
            patch(
                "codeframe.core.adapters.verification_wrapper.find_quick_fix",
                return_value=None,
            ),
            patch(
                "codeframe.core.adapters.verification_wrapper.blockers",
            ) as mock_blockers,
        ):
            mock_blocker = MagicMock()
            mock_blocker.id = "blocker-456"
            mock_blockers.create.return_value = mock_blocker

            wrapper = VerificationWrapper(
                mock_inner_adapter, mock_workspace, max_correction_rounds=2,
            )
            result = wrapper.run("t1", "prompt", Path("/tmp"))

            assert result.status == "blocked"
            assert result.blocker_question is not None
            mock_blockers.create.assert_called_once()


class TestDefaultMaxRetries:
    """Test default max_correction_rounds is 5."""

    def test_default_max_correction_rounds_is_five(
        self, mock_inner_adapter, mock_workspace,
    ):
        wrapper = VerificationWrapper(mock_inner_adapter, mock_workspace)
        assert wrapper._max_correction_rounds == 5


class TestBuildEscalationQuestion:
    """Tests for the shared build_escalation_question helper."""

    def test_includes_error_and_reason(self):
        tracker = FixAttemptTracker()
        question = build_escalation_question(
            "SyntaxError: invalid syntax",
            "Same error 3+ times",
            tracker,
        )
        assert "SyntaxError" in question
        assert "Same error 3+ times" in question
        assert "automated fixes are not working" in question

    def test_includes_attempted_fixes(self):
        tracker = FixAttemptTracker()
        tracker.record_attempt("err", "fix_1")
        tracker.record_attempt("err", "fix_2")
        question = build_escalation_question("err", "reason", tracker)
        assert "fix_1" in question
        assert "fix_2" in question

    def test_truncates_long_errors(self):
        tracker = FixAttemptTracker()
        long_error = "x" * 500
        question = build_escalation_question(long_error, "reason", tracker)
        assert len(question) < len(long_error) + 500  # Error truncated to 300


class TestIntegrationScenario:
    """Integration test: engine succeeds → gates fail → retry → gates pass."""

    def test_full_correction_flow(
        self, mock_inner_adapter, mock_workspace,
    ):
        """Simulate: adapter completes, gates fail, no quick fix, adapter
        re-invoked with error context, gates pass on second check."""
        passing = MagicMock()
        passing.passed = True
        passing.checks = []

        failing = MagicMock()
        failing.passed = False
        failing.get_error_summary.return_value = "test.py:1:1: E501 Line too long"
        check = MagicMock()
        check.name = "ruff"
        check.status = GateStatus.FAILED
        check.output = "test.py:1:1: E501 Line too long"
        failing.checks = [check]

        with (
            patch(
                "codeframe.core.adapters.verification_wrapper.run_gates",
            ) as mock_gates,
            patch(
                "codeframe.core.adapters.verification_wrapper.find_quick_fix",
                return_value=None,
            ),
        ):
            # Gate sequence: fail → pass (after adapter correction)
            mock_gates.side_effect = [failing, passing]

            events_captured: list[AgentEvent] = []
            wrapper = VerificationWrapper(
                mock_inner_adapter, mock_workspace, max_correction_rounds=5,
            )
            result = wrapper.run(
                "t1", "implement feature X", Path("/tmp"),
                on_event=events_captured.append,
            )

            assert result.status == "completed"
            assert mock_inner_adapter.run.call_count == 2

            # Verify event sequence
            event_types = [e.type for e in events_captured]
            assert "verification" in event_types
            assert "verification_failed" in event_types
            assert "verification_passed" in event_types

            # Verify error context was included in correction prompt
            correction_prompt = mock_inner_adapter.run.call_args_list[1][0][1]
            assert "Correction Round 1" in correction_prompt
            assert "ruff" in correction_prompt
