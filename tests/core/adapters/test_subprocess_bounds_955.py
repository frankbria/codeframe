"""The driver must not hand its stdin or its memory to the child (#955).

Two independent defects in ``SubprocessAdapter.run``:

* ``stdin=... if stdin_content else None``. ``None`` *inherits* the parent's
  stdin, so a CLI that probes for a TTY concludes it is interactive and waits
  for input that never arrives — the run then burns its whole timeout having
  done nothing.
* stdout was accumulated in an unbounded list and stderr read in one unbounded
  ``read()``. A chatty or looping agent streams for the entire timeout window,
  so how much of the driver's memory it consumed was the child's decision.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from codeframe.core.adapters import subprocess_adapter as sa
from codeframe.core.adapters.subprocess_adapter import SubprocessAdapter

pytestmark = pytest.mark.v2


def _py_adapter(script: str, *, stdin: str | None = None, timeout_s: int = 30):
    """An adapter that runs `script` under this interpreter."""

    class _PyAdapter(SubprocessAdapter):
        def build_command(self, prompt, workspace_path):
            return [sys.executable, "-c", script]

        def get_stdin(self, prompt):
            return stdin

    with patch("shutil.which", return_value=sys.executable):
        return _PyAdapter("python", timeout_s=timeout_s)


@pytest.fixture(autouse=True)
def _no_git():
    with patch.object(SubprocessAdapter, "_detect_modified_files", return_value=[]):
        yield


class TestStdinIsNeverInherited:
    """`None` would inherit the parent's stdin; DEVNULL answers every TTY probe."""

    def _popen_stdin_kwarg(self, adapter) -> object:
        with patch("subprocess.Popen", side_effect=RuntimeError("stop")) as popen:
            with pytest.raises(RuntimeError):
                adapter.run("t", "prompt", Path("/tmp"))
        return popen.call_args.kwargs["stdin"]

    def test_no_stdin_content_uses_devnull_not_none(self):
        assert self._popen_stdin_kwarg(_py_adapter("pass")) is subprocess.DEVNULL

    def test_stdin_content_still_uses_a_pipe(self):
        adapter = _py_adapter("pass", stdin="the prompt")
        assert self._popen_stdin_kwarg(adapter) is subprocess.PIPE

    def test_child_reading_stdin_gets_eof_immediately(self, tmp_path):
        """End-to-end: a child that reads stdin must not stall waiting on it."""
        script = (
            "import sys\n"
            "print('ISATTY', sys.stdin.isatty())\n"
            "print('READ', repr(sys.stdin.read()))\n"
        )
        start = time.monotonic()
        result = _py_adapter(script, timeout_s=15).run("t", "go", tmp_path)
        elapsed = time.monotonic() - start

        assert result.status == "completed"
        assert "ISATTY False" in result.output
        assert "READ ''" in result.output
        assert elapsed < 15  # returned on its own, not bounded by the timeout


class TestStdoutIsBounded:
    def test_retention_is_capped_but_streaming_stays_lossless(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(sa, "MAX_RETAINED_STDOUT_LINES", 50)
        script = "for i in range(200): print(f'line-{i}', flush=True)"

        streamed: list[str] = []
        result = _py_adapter(script).run(
            "t", "go", tmp_path, on_event=lambda e: streamed.append(e.data["line"])
        )

        assert result.status == "completed"
        # `on_event` sees every line — the cap bounds retention, not streaming.
        assert len(streamed) == 200
        assert streamed[0] == "line-0"

        body = result.output.splitlines()
        assert len(body) == 51  # 50 retained + the truncation notice
        assert "150 earlier line(s) truncated" in body[0]
        # The tail is kept, because that is where an agent's conclusion lives.
        assert body[-1] == "line-199"
        assert "line-0\n" not in result.output

    def test_output_under_the_cap_is_verbatim(self, tmp_path, monkeypatch):
        """No truncation notice when nothing was dropped."""
        monkeypatch.setattr(sa, "MAX_RETAINED_STDOUT_LINES", 50)
        script = "for i in range(10): print(f'line-{i}', flush=True)"

        result = _py_adapter(script).run("t", "go", tmp_path)

        assert result.output.splitlines() == [f"line-{i}" for i in range(10)]
        assert "truncated" not in result.output


class TestStderrIsBounded:
    def test_retention_is_capped_and_the_child_never_blocks(
        self, tmp_path, monkeypatch
    ):
        """Draining must continue past the cap, or the child deadlocks on a full pipe.

        That deadlock is precisely what the drain thread exists to prevent, so
        capping by *stopping the read* would reintroduce it. 200 KB against a
        ~64 KB pipe buffer means an undrained child could not finish.
        """
        monkeypatch.setattr(sa, "MAX_RETAINED_STDERR_CHARS", 1000)
        script = (
            "import sys\n"
            "sys.stderr.write('E' * (200 * 1024)); sys.stderr.flush()\n"
            "sys.exit(1)\n"
        )

        start = time.monotonic()
        result = _py_adapter(script, timeout_s=30).run("t", "go", tmp_path)
        elapsed = time.monotonic() - start

        assert elapsed < 30  # the child exited; it was not killed at the timeout
        assert result.error is not None
        assert len(result.error) <= 1000
