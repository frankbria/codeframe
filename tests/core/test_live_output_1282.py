"""#1282: live output that never ended, and output that never arrived.

- `cf work follow` checked for completion only when a new line arrived, so a
  finished run with no more output was followed forever.
- External engines never wrote `output.log`: only the builtin engines were
  handed the output logger.
- The task SSE stream listened only to the in-process publisher, so a task run
  by a batch subprocess showed heartbeats forever.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest
from typer.testing import CliRunner

from codeframe.core import runtime, streaming, tasks
from codeframe.core.state_machine import TaskStatus
from codeframe.core.workspace import create_or_load_workspace

pytestmark = [pytest.mark.v2, pytest.mark.timeout(60)]


@pytest.fixture
def ws(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    return create_or_load_workspace(repo)


def _running(ws):
    task = tasks.create(ws, title="t", status=TaskStatus.READY)
    return task, runtime.start_task_run(ws, task.id)


# ---------------------------------------------------------------------------
# cf work follow
# ---------------------------------------------------------------------------


class TestFollowEndsWithTheRun:
    def test_tail_stops_when_told_to_even_with_no_new_lines(self, ws):
        _task, run = _running(ws)
        stop = threading.Event()
        threading.Timer(0.5, stop.set).start()
        start = time.monotonic()

        list(streaming.tail_run_output(ws, run.id, poll_interval=0.1, should_stop=stop.is_set))

        assert time.monotonic() - start < 3

    def test_tail_stops_on_a_quiet_log_that_exists(self, ws):
        """The common case: the run wrote output, then fell silent and ended."""
        _task, run = _running(ws)
        log = streaming.RunOutputLogger(ws, run.id)
        log.write("working\n")
        log.close()
        stop = threading.Event()
        threading.Timer(0.5, stop.set).start()
        start = time.monotonic()

        lines = list(streaming.tail_run_output(ws, run.id, poll_interval=0.1, should_stop=stop.is_set))

        assert lines == ["working\n"]
        assert time.monotonic() - start < 3

    def test_lines_written_before_the_stop_are_still_yielded(self, ws):
        _task, run = _running(ws)
        log = streaming.RunOutputLogger(ws, run.id)
        log.write("last words\n")
        log.close()

        lines = list(
            streaming.tail_run_output(ws, run.id, poll_interval=0.1, should_stop=lambda: True)
        )

        assert lines == ["last words\n"]

    def test_follow_returns_soon_after_the_run_completes(self, ws):
        """No --timeout: only the run's completion can end it."""
        from codeframe.cli.app import app

        task, run = _running(ws)
        threading.Timer(0.5, lambda: runtime.complete_run(ws, run.id)).start()
        start = time.monotonic()

        result = CliRunner().invoke(app, ["work", "follow", task.id, "-w", str(ws.repo_path)])

        assert time.monotonic() - start < 5, "follow kept waiting after the run finished"
        assert "COMPLETED" in result.output


# ---------------------------------------------------------------------------
# External engines write output.log
# ---------------------------------------------------------------------------


class TestExternalEnginesWriteTheOutputLog:
    def test_a_stub_external_adapters_lines_reach_output_log(self, ws, monkeypatch):
        from codeframe.core import engine_registry
        from codeframe.core.adapters.agent_adapter import AgentEvent, AgentResult

        class StubCLI:
            name = "claude-code"

            def run(self, task_id, prompt, workspace_path, on_event=None):
                for line in ("reading the repo", "editing app.py"):
                    on_event(AgentEvent(type="output", data={"line": line}))
                on_event(AgentEvent(type="progress", message="Completed fileChange"))
                return AgentResult(status="failed", output="", error="stub stops here")

        monkeypatch.setattr(engine_registry, "get_external_adapter", lambda *a, **k: StubCLI())
        _task, run = _running(ws)

        runtime.execute_agent(ws, run, engine="claude-code")

        text = streaming.get_run_output_path(ws, run.id).read_text(encoding="utf-8")
        assert "reading the repo" in text and "editing app.py" in text
        assert "Completed fileChange" in text


# ---------------------------------------------------------------------------
# The task SSE stream ends without the in-process publisher
# ---------------------------------------------------------------------------


class _Connected:
    async def is_disconnected(self):
        return False


class TestTheStreamNoticesAnOutOfProcessCompletion:
    def test_a_completion_the_publisher_never_saw_ends_the_stream(self):
        """A batch subprocess finishes the run; nothing is published here."""
        from codeframe.core.models import CompletionEvent
        from codeframe.core.streaming import EventPublisher
        from codeframe.ui.streaming_utils import event_stream_generator

        checks = {"n": 0}

        def terminal():
            checks["n"] += 1
            if checks["n"] < 3:  # live at subscribe time and for a heartbeat
                return None
            return CompletionEvent(task_id="t", status="completed", duration_seconds=1.0)

        async def collect():
            out = []
            gen = event_stream_generator(
                "t", EventPublisher(), _Connected(), heartbeat_interval=0.1,
                after_subscribe=terminal,
            )
            async for chunk in gen:
                out.append(chunk)
            return out

        chunks = asyncio.run(asyncio.wait_for(collect(), timeout=10))

        assert any("completion" in c for c in chunks), chunks


# ---------------------------------------------------------------------------
# Review findings
# ---------------------------------------------------------------------------


HOSTILE = "arr[/bold] and [red]not red[/red]"


class TestReviewFindings:
    def test_follow_prints_agent_output_literally(self, ws):
        """Raw agent stdout now reaches output.log; a stray closing tag used to
        raise MarkupError and kill the command."""
        from codeframe.cli.app import app

        task, run = _running(ws)
        log = streaming.RunOutputLogger(ws, run.id)
        log.write(HOSTILE + "\n")
        log.close()
        threading.Timer(0.3, lambda: runtime.complete_run(ws, run.id)).start()

        result = CliRunner().invoke(app, ["work", "follow", task.id, "-w", str(ws.repo_path)])

        assert result.exit_code == 0, result.output
        assert HOSTILE in result.output

    def test_a_write_after_close_is_dropped_not_raised(self, ws):
        """A reader thread that outlives the run must keep draining its pipe."""
        _task, run = _running(ws)
        log = streaming.RunOutputLogger(ws, run.id)
        log.close()

        log.write("late line\n")  # must not raise

    def test_a_failing_recheck_does_not_end_a_live_stream(self):
        from codeframe.core.models import CompletionEvent
        from codeframe.core.streaming import EventPublisher
        from codeframe.ui.streaming_utils import event_stream_generator

        checks = {"n": 0}

        def flaky():
            checks["n"] += 1
            if checks["n"] == 2:
                raise RuntimeError("database is locked")
            if checks["n"] < 4:
                return None
            return CompletionEvent(task_id="t", status="completed", duration_seconds=1.0)

        async def collect():
            out = []
            async for chunk in event_stream_generator(
                "t", EventPublisher(), _Connected(), heartbeat_interval=0.1,
                after_subscribe=flaky,
            ):
                out.append(chunk)
            return out

        chunks = asyncio.run(asyncio.wait_for(collect(), timeout=10))
        assert any("completion" in c for c in chunks)

    def test_codex_agent_messages_reach_output_log(self, ws, monkeypatch):
        from codeframe.core import engine_registry
        from codeframe.core.adapters.agent_adapter import AgentEvent, AgentResult

        class StubCodex:
            name = "codex"

            def run(self, task_id, prompt, workspace_path, on_event=None):
                on_event(AgentEvent(
                    type="progress", message="Completed agentMessage",
                    data={"type": "agentMessage", "text": "I added the search endpoint."},
                ))
                return AgentResult(status="failed", error="stub stops here")

        monkeypatch.setattr(engine_registry, "get_external_adapter", lambda *a, **k: StubCodex())
        _task, run = _running(ws)

        runtime.execute_agent(ws, run, engine="codex")

        text = streaming.get_run_output_path(ws, run.id).read_text(encoding="utf-8")
        assert "I added the search endpoint." in text

