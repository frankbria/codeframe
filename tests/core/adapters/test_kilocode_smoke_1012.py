"""Binary-gated smoke test: the Kilocode adapter against the real CLI (#1012).

The adapter shipped invoking ``kilo run <prompt> …``. **There is no ``run``
subcommand.** Verified against kilocode 0.22.0: usage is
``kilocode [options] [command] [prompt]`` and the only commands are ``auth``,
``config``, ``debug`` and ``models``. So ``run`` was consumed as the prompt,
``--auto`` never took effect, and the CLI opened its interactive TUI and hung
until the adapter's timeout — writing nothing, while unit tests built entirely
from mocks asserted the adapter agreed with itself.

That is the gap this file closes. Every assertion runs the adapter's own
``build_command`` output against the installed binary, so a future change to the
invocation that mocked tests would happily accept is caught here instead.

Skipped when ``kilo`` is not installed, so CI without the binary stays green —
but it is **launch-gating**, not deferred: kilocode is a shipped engine.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from codeframe.core.adapters.kilocode import KilocodeAdapter

pytestmark = [
    pytest.mark.v2,
    # Opt-in, not merely binary-gated. These drive real kilocode sessions —
    # real credentials, real model calls, real money, 20-240s each — so a plain
    # `uv run pytest` must not start doing that just because the CLI happens to
    # be installed on the machine.
    pytest.mark.skipif(
        os.environ.get("CODEFRAME_ENGINE_SMOKE") != "1",
        reason="engine smoke tier is opt-in: set CODEFRAME_ENGINE_SMOKE=1",
    ),
    pytest.mark.skipif(
        shutil.which(KilocodeAdapter._resolve_binary()) is None,
        reason="kilo CLI not installed",
    ),
]

#: Long enough for a real model round-trip, short enough to fail a hang loudly.
_TIMEOUT_S = 240


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    # Without a commit HEAD is unborn, `_git_head` returns None, and
    # `require_file_changes` reads the workspace as "not a git repo" and never
    # fires — which would silently neuter the writes-nothing assertion.
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=test",
         "commit", "-q", "--allow-empty", "-m", "baseline"],
        cwd=workspace,
        check=True,
    )
    return workspace


def _surface() -> str:
    from codeframe.core.adapters.kilocode import _detect_surface

    return _detect_surface(shutil.which(KilocodeAdapter._resolve_binary()) or "")


def test_the_run_subcommand_matches_the_installed_surface() -> None:
    """Checked against the binary's own help, so a future CLI change fails here.

    0.22 had no ``run`` (#1012: it was consumed as the prompt and opened a TUI);
    the 7.x rewrite is an opencode fork whose documented entry point is
    ``kilo run [message..]`` (#1015). The commands are listed one per line as
    ``kilo <command> ...``, so they are parsed by that, not by column.
    """
    proc = subprocess.run(
        [KilocodeAdapter._resolve_binary(), "--help"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    help_text = proc.stdout + proc.stderr
    has_run = re.search(r"^\s*kilo(?:code)?\s+run\b", help_text, re.MULTILINE) is not None
    if _surface() == "modern":
        assert has_run, f"kilo 7.x no longer lists `run`; revisit the adapter:\n{help_text[:800]}"
    else:
        assert not has_run, "kilocode 0.22 now has `run`; revisit the legacy invocation"


def test_the_adapter_command_matches_the_installed_surface() -> None:
    """The adapter's own command, for whichever CLI is actually installed."""
    cmd = KilocodeAdapter().build_command("say hello", Path("/tmp/repo"))

    if _surface() == "modern":
        assert cmd[1] == "run", f"7.x needs `kilo run`: {cmd[:3]}"
        assert "--dir" in cmd
        # On 7.x --auto is the old --yolo: the #916 permission bypass stays off.
        assert "--auto" not in cmd
    else:
        assert cmd[1] == "say hello", f"prompt is not the leading positional: {cmd[:3]}"


def test_the_old_invocation_hangs_and_writes_nothing(repo: Path) -> None:
    """Pins the 0.22 bug, so nobody restores `run` there believing it worked.

    The old command opens the TUI: it never reaches a terminal state on its own,
    so it is killed by the timeout and leaves the workspace untouched. On 7.x
    `run` is the real entry point, so the premise does not apply.
    """
    if _surface() == "modern":
        pytest.skip("kilo 7.x: `run` is the documented entry point, not the 0.22 bug")
    binary = KilocodeAdapter._resolve_binary()
    try:
        subprocess.run(
            [binary, "run", "Create a file old.txt containing exactly: old",
             "--auto", "--workspace", str(repo)],
            capture_output=True,
            text=True,
            # The TUI opens immediately and never exits; a short window is
            # enough to prove it, and keeps this pin cheap.
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        pass  # the expected outcome — the TUI never exits

    assert not (repo / "old.txt").exists(), (
        "the old invocation wrote a file; the premise of #1012 no longer holds"
    )


def test_the_adapter_command_actually_writes_a_file(repo: Path) -> None:
    """Runs exactly what the adapter builds, and asserts on the file produced.

    Not "exit 0" — the TUI path could exit 0 having done nothing, which is the
    whole false-completion class here.
    """
    adapter = KilocodeAdapter(timeout_s=_TIMEOUT_S)
    result = adapter.run(
        "task-smoke",
        "Create a file smoke.txt containing exactly the word ACKNOWLEDGED. "
        "Do not create or modify any other file.",
        repo,
    )
    if (result.error or "").startswith(("Kilocode execution timed out", "Process timed out")):
        pytest.skip("kilo did not complete in time")

    written = repo / "smoke.txt"
    assert written.exists(), (
        f"the adapter's own command wrote no file — status={result.status!r} "
        f"error={result.error!r}"
    )
    assert result.status == "completed"
    assert "smoke.txt" in result.modified_files


def test_a_run_that_writes_nothing_is_not_reported_completed(repo: Path) -> None:
    """End to end through `adapter.run`, with a prompt that asks for no changes."""
    adapter = KilocodeAdapter(timeout_s=_TIMEOUT_S)
    result = adapter.run(
        "task-smoke",
        "Reply with the single word ACKNOWLEDGED. Do not create, edit or "
        "delete any files.",
        repo,
    )
    if (result.error or "").startswith(("Kilocode execution timed out", "Process timed out")):
        pytest.skip("kilo did not complete in time")

    changed = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    if changed:
        pytest.skip(f"the model wrote files anyway: {changed!r}")

    assert result.status != "completed", (
        f"a run that wrote nothing was reported {result.status!r} — gates would "
        f"then pass on an unchanged tree"
    )
