"""Binary-gated smoke test: the OpenCode adapter against the real CLI (#913).

The adapter shipped invoking ``opencode --non-interactive`` with the prompt on
stdin. **No such flag exists.** Verified against opencode 1.18.7: it is absent
from the option list, and passing it starts the TUI — so the delegated run did
no work, exited non-zero on the help path, and unit tests built entirely from
mocks could not tell.

That is the gap this file closes. Every assertion here runs the adapter's own
``build_command`` output against the installed binary, so a future change to
the invocation that unit tests would happily mock is caught here instead.

Skipped when ``opencode`` is not installed, so CI without the binary stays
green — but it is **launch-gating**, not deferred: the engine is one of the
shipped multi-model options.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from codeframe.core.adapters.opencode import OpenCodeAdapter

pytestmark = [
    pytest.mark.v2,
    # Opt-in, not merely binary-gated. These drive real opencode sessions —
    # real credentials, real model calls, real money — so a plain
    # `uv run pytest` must not start doing that just because the CLI happens to
    # be installed on the machine. (#1012 review)
    pytest.mark.skipif(
        os.environ.get("CODEFRAME_ENGINE_SMOKE") != "1",
        reason="engine smoke tier is opt-in: set CODEFRAME_ENGINE_SMOKE=1",
    ),
    pytest.mark.skipif(
        shutil.which("opencode") is None, reason="opencode CLI not installed"
    ),
]

#: Long enough for a real model round-trip, short enough to fail a hang loudly.
_TIMEOUT_S = 240


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    # A repo with no commits has an unborn HEAD, so `git rev-parse HEAD` fails,
    # `_git_head` returns None, and `require_file_changes` reads the workspace as
    # "not a git repo" and never fires — which would silently neuter the
    # writes-nothing assertion below. Give it a baseline commit.
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=test",
         "commit", "-q", "--allow-empty", "-m", "baseline"],
        cwd=workspace,
        check=True,
    )
    return workspace


def test_the_run_subcommand_exists_and_non_interactive_does_not() -> None:
    """The assumption that produced the bug, checked against the binary.

    Asserted on the CLI's own help rather than on our code, so this fails if a
    future opencode release moves the headless entry point out from under us.
    """
    proc = subprocess.run(
        ["opencode", "--help"], capture_output=True, text=True, timeout=60
    )
    # opencode prints help on stderr, not stdout.
    help_text = proc.stdout + proc.stderr

    assert "opencode run" in help_text, "the headless entry point moved"
    assert "--non-interactive" not in help_text, (
        "--non-interactive now exists; revisit the adapter's invocation"
    )


def test_the_adapter_command_actually_writes_a_file(repo: Path) -> None:
    """Runs exactly what the adapter builds, and asserts on the file it produces.

    Not "exit 0" — the old invocation could exit 0 and do nothing, which is the
    whole false-completion class here.
    """
    adapter = OpenCodeAdapter()
    cmd = adapter.build_command(
        "Create a file named smoke.txt containing exactly the word: works", repo
    )

    try:
        proc = subprocess.run(
            cmd, cwd=repo, capture_output=True, text=True, timeout=_TIMEOUT_S
        )
    except subprocess.TimeoutExpired:
        pytest.skip(f"opencode did not complete within {_TIMEOUT_S}s")

    produced = repo / "smoke.txt"
    if not produced.exists() and "smoke.txt" in proc.stdout:
        # opencode reported writing the file but it is not in the workspace —
        # it resolves its project directory from the *parent* process, ignoring
        # the subprocess cwd every other adapter relies on. Tracked as
        # #1007 [P0.27]; distinct from this issue's contract.
        pytest.xfail("opencode ignored cwd and wrote outside the workspace")

    assert produced.exists(), (
        f"the adapter's command wrote nothing.\n"
        f"cmd={cmd}\nstdout={proc.stdout[-2000:]}\nstderr={proc.stderr[-2000:]}"
    )
    assert "works" in produced.read_text()


def test_the_old_invocation_does_no_work(repo: Path) -> None:
    """Pins the actual bug, so nobody restores the flag believing it worked.

    ``opencode --non-interactive`` prints the banner/usage and writes nothing.
    """
    proc = subprocess.run(
        ["opencode", "--non-interactive"],
        cwd=repo,
        input="Create a file named old.txt containing: works",
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert not (repo / "old.txt").exists(), (
        "the old invocation wrote a file; the premise of #913 no longer holds"
    )
    assert proc.returncode != 0 or "Commands:" in proc.stdout


def test_a_run_that_writes_nothing_is_not_reported_completed(repo: Path) -> None:
    """End to end through `adapter.run`, in a real git repo, with a prompt that
    asks for no file changes — the guard must catch it."""
    # Bound the run: SubprocessAdapter.run catches TimeoutExpired itself and
    # returns status="failed", so it never propagates — catching it here would
    # be dead code, and without an explicit timeout an opencode hang would sit
    # on the 30-minute default and then "pass" for the wrong reason.
    adapter = OpenCodeAdapter(timeout_s=_TIMEOUT_S)

    result = adapter.run(
        "task-smoke",
        "Reply with the single word ACKNOWLEDGED. Do not create, edit or "
        "delete any files.",
        repo,
    )
    if (result.error or "").startswith("Process timed out"):
        pytest.skip("opencode did not complete in time")

    changed = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()

    if changed:
        pytest.skip(f"the model wrote files anyway: {changed!r}")

    assert result.status != "completed", (
        f"a run that wrote nothing was reported {result.status!r} — gates would "
        f"then pass on an unchanged tree"
    )
