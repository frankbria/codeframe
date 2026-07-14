"""Tests for 'cf events tail' and 'cf gates run' (issue #770).

Both commands were help-advertised stubs printing "Not yet implemented".
These tests lock in the wired behavior: events tail wraps
core.events.list_recent/tail; gates run wraps core.gates.run (via review).

Real SQLite workspace via CliRunner; only the infinite tail loop and the
gate subprocess runner are mocked.
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core import events
from codeframe.core.events import Event
from codeframe.core.gates import GateCheck, GateResult, GateStatus
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2

runner = CliRunner()


@pytest.fixture()
def ws(tmp_path: Path):
    """Initialised workspace — returns (workspace_object, workspace_path)."""
    workspace = create_or_load_workspace(tmp_path)
    return workspace, tmp_path


@pytest.fixture()
def ws_with_events(ws):
    """Workspace seeded with two events; returns (workspace, path, [event, event])."""
    workspace, path = ws
    e1 = events.emit_for_workspace(
        workspace, "TASK_STARTED", {"task_id": "abc12345"}, print_event=False
    )
    e2 = events.emit_for_workspace(
        workspace, "TASK_COMPLETED", {"task_id": "abc12345"}, print_event=False
    )
    return workspace, path, [e1, e2]


def _fake_event(event_id: int, event_type: str = "GATE_PASSED") -> Event:
    return Event(
        id=event_id,
        workspace_id="w1",
        event_type=event_type,
        payload={},
        created_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# cf events tail
# ---------------------------------------------------------------------------


class TestEventsTail:
    def test_prints_recent_events_then_exits_when_tail_ends(self, ws_with_events):
        _, path, seeded = ws_with_events
        with patch("codeframe.core.events.tail", return_value=iter([])) as mock_tail:
            result = runner.invoke(app, ["events", "tail", "-w", str(path)])
        assert result.exit_code == 0, result.output
        assert "Not yet implemented" not in result.output
        assert "TASK_STARTED" in result.output
        assert "TASK_COMPLETED" in result.output
        # follows from the newest already-printed event
        assert mock_tail.call_args.kwargs.get("since_id") == seeded[-1].id

    def test_respects_limit_option(self, ws_with_events):
        _, path, _ = ws_with_events
        with patch("codeframe.core.events.tail", return_value=iter([])):
            result = runner.invoke(app, ["events", "tail", "-w", str(path), "-n", "1"])
        assert result.exit_code == 0, result.output
        # newest only
        assert "TASK_COMPLETED" in result.output
        assert "TASK_STARTED" not in result.output

    def test_prints_followed_events(self, ws_with_events):
        _, path, _ = ws_with_events
        new_event = _fake_event(99, "BATCH_COMPLETED")
        with patch("codeframe.core.events.tail", return_value=iter([new_event])):
            result = runner.invoke(app, ["events", "tail", "-w", str(path)])
        assert result.exit_code == 0, result.output
        assert "BATCH_COMPLETED" in result.output

    def test_keyboard_interrupt_exits_cleanly(self, ws_with_events):
        _, path, _ = ws_with_events

        def interrupted(*args, **kwargs):
            yield _fake_event(50)
            raise KeyboardInterrupt

        with patch("codeframe.core.events.tail", side_effect=interrupted):
            result = runner.invoke(app, ["events", "tail", "-w", str(path)])
        assert result.exit_code == 0, result.output

    def test_no_workspace_exits_with_error(self, tmp_path):
        result = runner.invoke(app, ["events", "tail", "-w", str(tmp_path)])
        assert result.exit_code == 1
        assert "No workspace found" in result.output


# ---------------------------------------------------------------------------
# cf gates run
# ---------------------------------------------------------------------------


def _gate_result(passed: bool) -> GateResult:
    status = GateStatus.PASSED if passed else GateStatus.FAILED
    check = GateCheck(name="pytest", status=status, output="" if passed else "boom", duration_ms=5)
    return GateResult(passed=passed, checks=[check])


class TestGatesRun:
    def test_runs_gates_and_reports_pass(self, ws):
        _, path = ws
        with patch("codeframe.core.gates.run", return_value=_gate_result(True)) as mock_run:
            result = runner.invoke(app, ["gates", "run", "-w", str(path)])
        assert result.exit_code == 0, result.output
        assert "Not yet implemented" not in result.output
        assert "pytest" in result.output
        assert "PASSED" in result.output
        assert mock_run.call_count == 1

    def test_failure_exits_nonzero_and_shows_output(self, ws):
        _, path = ws
        with patch("codeframe.core.gates.run", return_value=_gate_result(False)):
            result = runner.invoke(app, ["gates", "run", "-w", str(path)])
        assert result.exit_code == 1
        assert "FAILED" in result.output
        assert "boom" in result.output

    def test_gate_option_passthrough(self, ws):
        _, path = ws
        with patch("codeframe.core.gates.run", return_value=_gate_result(True)) as mock_run:
            result = runner.invoke(
                app, ["gates", "run", "-w", str(path), "--gate", "pytest"]
            )
        assert result.exit_code == 0, result.output
        assert mock_run.call_args.kwargs.get("gates") == ["pytest"]

    def test_no_workspace_exits_with_error(self, tmp_path):
        result = runner.invoke(app, ["gates", "run", "-w", str(tmp_path)])
        assert result.exit_code == 1
        assert "No workspace found" in result.output


# ---------------------------------------------------------------------------
# public event formatter (promoted from _print_event/_get_event_color)
# ---------------------------------------------------------------------------


class TestPublicEventFormatter:
    def test_public_functions_exist(self):
        assert callable(events.print_event)
        assert callable(events.get_event_color)

    def test_color_mapping_preserved(self):
        assert events.get_event_color("TASK_FAILED") == "red"
        assert events.get_event_color("TASK_COMPLETED") == "green"
        assert events.get_event_color("TASK_STARTED") == "blue"
        assert events.get_event_color("TASK_BLOCKED") == "yellow"
        assert events.get_event_color("SOMETHING_ELSE") == "cyan"
