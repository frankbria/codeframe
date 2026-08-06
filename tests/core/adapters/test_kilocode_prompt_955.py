"""The kilo prompt must not travel on argv (#955).

argv is world-readable: ``ps`` shows every element to every user on the machine,
so a prompt carrying task context and file excerpts was on display for the whole
run. It is also bounded — Linux caps a *single* argv entry at 128 KiB, under
CodeFrame's ~100K-token budget — which #1015 already worked around by routing
only *oversized* prompts to stdin. Size was never the whole problem; stdin is now
the only modern path.

Legacy 0.22.0 is unchanged: it has no stdin path at all, so sending the prompt
there would silently do nothing.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from codeframe.core.adapters import kilocode as kilo_mod
from codeframe.core.adapters.kilocode import KilocodeAdapter

pytestmark = pytest.mark.v2

_FIXTURES = Path(__file__).parent / "fixtures" / "kilocode_help"
_LEGACY_HELP = (_FIXTURES / "help-0.22.0.txt").read_text()
_MODERN_HELP = (_FIXTURES / "help-7.4.17.txt").read_text()

_PROMPT = "refactor the widget parser and keep the API stable"


@pytest.fixture(autouse=True)
def _clear_surface_cache():
    kilo_mod._SURFACE_CACHE.clear()
    yield
    kilo_mod._SURFACE_CACHE.clear()


@pytest.fixture
def adapter():
    a = KilocodeAdapter.__new__(KilocodeAdapter)
    a._binary_path = "/usr/local/bin/kilo"
    a._cli_args = []
    # run() reads these; __new__ skips __init__ so they are set by hand.
    a._timeout_s = 30
    a._require_file_changes = False
    return a


def _with_help(monkeypatch, help_text: str) -> None:
    class _Proc:
        stdout = help_text.encode("utf-8")
        stderr = b""

    monkeypatch.setattr(kilo_mod.subprocess, "run", lambda *a, **k: _Proc())


class TestModernKeepsThePromptOffArgv:
    def test_no_argv_element_contains_the_prompt(self, adapter, monkeypatch, tmp_path):
        _with_help(monkeypatch, _MODERN_HELP)

        cmd = adapter.build_command(_PROMPT, tmp_path)

        assert _PROMPT not in cmd
        # Not merely absent as a whole element — no fragment of it leaks either.
        assert not any("widget parser" in part for part in cmd)

    def test_the_prompt_goes_to_stdin_instead(self, adapter, monkeypatch, tmp_path):
        _with_help(monkeypatch, _MODERN_HELP)

        assert adapter.get_stdin(_PROMPT) == _PROMPT

    def test_the_invocation_is_otherwise_unchanged(self, adapter, monkeypatch, tmp_path):
        """`run --dir` and the withheld --auto (#916/#1015) must survive this."""
        _with_help(monkeypatch, _MODERN_HELP)

        cmd = adapter.build_command(_PROMPT, tmp_path)

        assert cmd == ["/usr/local/bin/kilo", "run", "--dir", str(tmp_path)]
        assert "--auto" not in cmd and "--yolo" not in cmd

    @pytest.mark.parametrize("size", [10, 200_000])
    def test_stdin_is_used_regardless_of_size(
        self, adapter, monkeypatch, tmp_path, size
    ):
        """The 128 KiB argv ceiling no longer decides the path — nothing does."""
        _with_help(monkeypatch, _MODERN_HELP)
        prompt = "x" * size

        assert adapter.build_command(prompt, tmp_path) == [
            "/usr/local/bin/kilo", "run", "--dir", str(tmp_path),
        ]
        assert adapter.get_stdin(prompt) == prompt


class TestLegacyIsUnchanged:
    def test_legacy_still_takes_the_prompt_positionally(
        self, adapter, monkeypatch, tmp_path
    ):
        _with_help(monkeypatch, _LEGACY_HELP)

        cmd = adapter.build_command(_PROMPT, tmp_path)

        assert cmd[1] == _PROMPT
        assert adapter.get_stdin(_PROMPT) is None


class TestTheRunnerPipesIt:
    def test_run_opens_a_stdin_pipe_for_a_modern_prompt(
        self, adapter, monkeypatch, tmp_path
    ):
        """A prompt sent to stdin is only delivered if run() opens the pipe.

        get_stdin returning the prompt drives `stdin=PIPE` in SubprocessAdapter;
        if that link broke, kilo would get no message and no argv either.
        """
        _with_help(monkeypatch, _MODERN_HELP)

        with patch("subprocess.Popen", side_effect=RuntimeError("stop")) as popen:
            with pytest.raises(RuntimeError):
                adapter.run("t", _PROMPT, tmp_path)

        assert popen.call_args.kwargs["stdin"] is subprocess.PIPE


class TestUnreadableHelpFallsBackToModern:
    """"Not modern" is not the same claim as "legacy" (#955).

    The surface used to be picked by elimination, so any ``--help`` output
    lacking the modern marker counted as evidence *for* legacy — including
    output that was not help text at all. A sandboxed kilo whose log directory
    is read-only prints a Bun stack trace and exits 1; the adapter then emitted
    ``--auto --workspace`` at a 7.x CLI, where ``--auto`` is the permission
    bypass #916 established must stay off.
    """

    _EROFS_CRASH = (
        "Error: Unexpected error\n\n"
        'Unknown: FileSystem.open (/home/u/.local/share/kilo/log/opencode.log",\n'
        ' syscall: "open",\n   errno: -30,\n    code: "EROFS"\n\n'
        "Bun v1.3.14 (Linux x64 baseline)\n"
    )

    @pytest.mark.parametrize(
        "help_text",
        [
            _EROFS_CRASH,
            "",  # nothing at all on either stream
            "kilo: command failed",
        ],
    )
    def test_output_that_is_not_help_selects_modern(self, monkeypatch, help_text):
        _with_help(monkeypatch, help_text)

        assert kilo_mod._detect_surface("/usr/local/bin/kilo") == kilo_mod._MODERN

    def test_a_crashing_help_does_not_emit_the_permission_bypass(
        self, adapter, monkeypatch, tmp_path
    ):
        """The consequence that made this worth fixing."""
        _with_help(monkeypatch, self._EROFS_CRASH)

        cmd = adapter.build_command(_PROMPT, tmp_path)

        assert "--auto" not in cmd
        assert "--workspace" not in cmd
        assert cmd == ["/usr/local/bin/kilo", "run", "--dir", str(tmp_path)]

    def test_real_help_from_both_clis_still_detects_correctly(self, monkeypatch):
        """The captured fixtures are the guard against over-correcting."""
        _with_help(monkeypatch, _MODERN_HELP)
        assert kilo_mod._detect_surface("/usr/local/bin/kilo") == kilo_mod._MODERN

        kilo_mod._SURFACE_CACHE.clear()
        _with_help(monkeypatch, _LEGACY_HELP)
        assert kilo_mod._detect_surface("/usr/local/bin/kilo") == kilo_mod._LEGACY
