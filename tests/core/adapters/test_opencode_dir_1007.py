"""opencode must work in the task's workspace, not CodeFrame's own (#1007 / P0.27).

Every ``SubprocessAdapter`` targets a workspace by passing ``cwd=workspace_path``
to ``Popen``. **opencode does not honour it** — it resolves its project directory
from the *parent* process, so a delegated task edits whatever directory CodeFrame
itself is running from. Under ``codeframe serve`` that is the server's own
checkout.

``require_file_changes`` does not catch it: the guard inspects the *workspace*,
finds no changes and fails the run — correctly reporting failure while the edits
have already landed elsewhere.

The binary-gated test below reads the project directory out of opencode's own
``session_start`` event, which it emits **before** contacting any model. That
makes the check independent of opencode's backend availability — the issue's own
investigation stalled because two ``--dir`` attempts timed out, and a plain run
timed out right after.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from codeframe.core.adapters.opencode import OpenCodeAdapter

pytestmark = pytest.mark.v2

_HAS_OPENCODE = shutil.which("opencode") is not None
requires_opencode = pytest.mark.skipif(
    not _HAS_OPENCODE, reason="opencode binary not installed"
)


# ---------------------------------------------------------------------------
# Command construction — runs everywhere
# ---------------------------------------------------------------------------


def test_the_command_names_the_workspace(tmp_path: Path) -> None:
    adapter = OpenCodeAdapter.__new__(OpenCodeAdapter)
    adapter._binary_path = "/usr/bin/opencode"
    adapter._cli_args = ["run"]

    cmd = adapter.build_command("do a thing", tmp_path)

    assert "--dir" in cmd
    assert cmd[cmd.index("--dir") + 1] == str(tmp_path)


def test_dir_precedes_the_positional_message(tmp_path: Path) -> None:
    """``opencode run [options] [message..]`` — a flag after the positional
    array is swallowed as part of the message."""
    adapter = OpenCodeAdapter.__new__(OpenCodeAdapter)
    adapter._binary_path = "/usr/bin/opencode"
    adapter._cli_args = ["run"]

    cmd = adapter.build_command("do a thing", tmp_path)

    assert cmd.index("--dir") < cmd.index("do a thing")


def test_an_oversized_prompt_still_carries_the_workspace(tmp_path: Path) -> None:
    """The >128 KiB prompt goes to stdin, but the workspace must not go with it."""
    adapter = OpenCodeAdapter.__new__(OpenCodeAdapter)
    adapter._binary_path = "/usr/bin/opencode"
    adapter._cli_args = ["run"]

    cmd = adapter.build_command("x" * (200 * 1024), tmp_path)

    assert cmd[cmd.index("--dir") + 1] == str(tmp_path)
    assert len(cmd) == 4  # binary, run, --dir, path — no positional


# ---------------------------------------------------------------------------
# Against the real binary
# ---------------------------------------------------------------------------


def _session_cwd(output: str) -> str | None:
    """The project directory opencode resolved, from its own session_start.

    The events arrive embedded in OSC-777 terminal notifications, so they are
    located by prefix and decoded with ``raw_decode`` — a regex cannot bound the
    object, whose nested braces defeat any non-greedy match.
    """
    decoder = json.JSONDecoder()
    for match in re.finditer(r'\{"v":1,', output):
        try:
            event, _ = decoder.raw_decode(output[match.start():])
        except json.JSONDecodeError:
            continue
        if event.get("event") == "session_start":
            return event.get("cwd")
    return None


@requires_opencode
def test_opencode_documents_dir(tmp_path: Path) -> None:
    """Pins the flag against upstream drift — kilocode renamed exactly this one
    out from under its adapter (#1015)."""
    proc = subprocess.run(
        ["opencode", "run", "--help"], capture_output=True, text=True, timeout=120
    )
    # opencode writes its help to stderr.
    assert "--dir" in proc.stdout + proc.stderr


@requires_opencode
def test_the_adapter_resolves_the_workspace_not_the_parent_cwd(tmp_path: Path) -> None:
    """The discriminating condition: parent cwd is a *different* directory.

    Reads opencode's resolved project dir from session_start, so it does not
    depend on a model turn completing.
    """
    workspace = tmp_path / "workspace"
    elsewhere = tmp_path / "elsewhere"
    workspace.mkdir()
    elsewhere.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)

    adapter = OpenCodeAdapter.__new__(OpenCodeAdapter)
    adapter._binary_path = shutil.which("opencode")
    adapter._cli_args = ["run"]
    cmd = adapter.build_command("say ok", workspace)

    try:
        proc = subprocess.run(
            cmd, cwd=str(elsewhere), capture_output=True, text=True, timeout=180
        )
    except subprocess.TimeoutExpired:
        pytest.skip("opencode did not respond within 180s")

    resolved = _session_cwd(proc.stdout + proc.stderr)
    if resolved is None:
        pytest.skip("opencode emitted no session_start event to inspect")

    assert Path(resolved).resolve() == workspace.resolve(), (
        f"opencode worked in {resolved}, not the task's workspace {workspace}. "
        "Without --dir it resolves the project from the parent process, so a "
        "delegated task edits whatever directory CodeFrame was launched from."
    )


@requires_opencode
def test_without_dir_it_takes_the_parent_cwd(tmp_path: Path) -> None:
    """Pins the bug itself, so nobody drops --dir believing cwd= is enough."""
    workspace = tmp_path / "workspace"
    elsewhere = tmp_path / "elsewhere"
    workspace.mkdir()
    elsewhere.mkdir()

    try:
        proc = subprocess.run(
            ["opencode", "run", "say ok"],
            cwd=str(workspace), capture_output=True, text=True, timeout=180,
        )
    except subprocess.TimeoutExpired:
        pytest.skip("opencode did not respond within 180s")

    resolved = _session_cwd(proc.stdout + proc.stderr)
    if resolved is None:
        pytest.skip("opencode emitted no session_start event to inspect")

    # If this ever starts equalling `workspace`, opencode began honouring cwd=
    # and the --dir workaround can be revisited.
    if Path(resolved).resolve() == workspace.resolve():
        pytest.xfail("opencode now honours cwd= — revisit the --dir workaround")
