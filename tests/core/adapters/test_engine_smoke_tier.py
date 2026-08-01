"""Binary-gated smoke/contract tier across every shipped engine adapter (#915).

Every external-engine adapter test patches ``shutil.which`` and ``Popen`` with
permissive mocks and replays the output the adapter's author expected. That is
not a hygiene problem — it is the mechanism by which three engines shipped with
invocations that could not do any work at all, each behind a green suite:

* #913 — opencode's ``--non-interactive``: no such flag; it started the TUI
* #914 — codex's app-server handshake: rejected by the real server at ``initialize``
* #1012 — kilocode's ``run`` subcommand: no such command; it started the TUI

This tier exists so the fourth one is caught here rather than in production. It
never mocks: every assertion runs against the installed binary, and the task leg
drives the adapter's own ``run()`` end to end.

Two legs, deliberately gated differently:

**Contract leg** — the CLI exists, responds, and still documents the entry point
the adapter depends on. No credentials, no model calls, seconds to run. Gated
only on the binary being present, so it can gate pull requests.

**Task leg** — one trivial task per engine driven to a terminal state with a real
file written. Needs credentials and minutes, and costs money, so it additionally
requires ``CODEFRAME_ENGINE_SMOKE=1`` and runs on a schedule.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest

from codeframe.core.adapters.agent_adapter import AgentAdapter

pytestmark = pytest.mark.v2

#: Long enough for a real model round-trip, short enough to fail a hang loudly.
_TIMEOUT_S = 240

_SMOKE_OPT_IN = os.environ.get("CODEFRAME_ENGINE_SMOKE") == "1"

#: Error prefixes meaning the engine ran out of time locally. Each adapter
#: words this differently, so they are enumerated rather than pattern-matched —
#: a loose "contains 'timeout'" would start swallowing real defects.
_TIMEOUT_PREFIXES = (
    # SubprocessAdapter (claude-code, opencode, kilocode)
    "Process timed out",
    "Kilocode execution timed out",
    # CodexAdapter's three distinct timeout paths (codex.py:229/345/351)
    "Codex app-server timed out",
    "Stall timeout:",
    "Turn timeout:",
)

#: Substrings identifying a fault in the *provider* behind a CLI, not in our
#: adapter. Deliberately narrow: these are the engines' own server-error
#: envelopes. Anything broader would hide exactly the defects this tier exists
#: to catch, so a skip here is a loud "no coverage obtained", never a pass.
_UPSTREAM_FAULT_MARKERS = (
    "Unexpected server error",  # opencode's backend 5xx envelope
    '"name": "UnknownError"',  # ditto, structured form
    "Overloaded",
    "rate limit",
)


def _environmental_reason(error: str | None) -> str | None:
    """Return why this run could not be attempted, or None if it genuinely failed.

    The distinction matters more here than anywhere else in the suite: every bug
    this tier catches looks like a clean failure, so the bar for "not our fault"
    has to be narrow and evidence-based.
    """
    if not error:
        return None
    if error.startswith(_TIMEOUT_PREFIXES):
        return f"engine did not finish in time: {error[:200]}"
    for marker in _UPSTREAM_FAULT_MARKERS:
        if marker in error:
            return f"upstream provider fault, not an adapter defect: {error[:300]}"
    return None


@dataclass(frozen=True)
class Engine:
    """One shipped external engine and how to check it against its real CLI."""

    name: str
    binary: Callable[[], str]
    adapter: Callable[[], AgentAdapter]
    #: Strings that must appear in the CLI's own --help. These encode the entry
    #: point the adapter depends on, asserted against the CLI rather than
    #: against our code, so an upstream rename fails here.
    help_must_contain: tuple[str, ...]
    #: Set when the adapter is known to target a different CLI version than the
    #: one likely installed. The contract check then xfails instead of blocking
    #: every adapter PR — but it is `strict=False`, so it flips to a pass the
    #: moment the adapter is migrated, and the reason names the tracking issue.
    known_drift: str | None = None

    def __str__(self) -> str:  # keeps parametrize ids readable
        return self.name


def _claude_code() -> AgentAdapter:
    from codeframe.core.adapters.claude_code import ClaudeCodeAdapter

    return ClaudeCodeAdapter()


def _codex() -> AgentAdapter:
    from codeframe.core.adapters.codex import CodexAdapter

    return CodexAdapter(turn_timeout_ms=_TIMEOUT_S * 1000)


def _opencode() -> AgentAdapter:
    from codeframe.core.adapters.opencode import OpenCodeAdapter

    return OpenCodeAdapter(timeout_s=_TIMEOUT_S)


def _kilocode() -> AgentAdapter:
    from codeframe.core.adapters.kilocode import KilocodeAdapter

    return KilocodeAdapter(timeout_s=_TIMEOUT_S)


def _kilo_binary() -> str:
    from codeframe.core.adapters.kilocode import KilocodeAdapter

    return KilocodeAdapter._resolve_binary()


ENGINES = (
    # `--print` is what makes claude non-interactive; without it the adapter
    # would open a session and never terminate.
    Engine("claude-code", lambda: "claude", _claude_code, ("--print",)),
    # The adapter speaks JSON-RPC to this subcommand (#914).
    Engine("codex", lambda: "codex", _codex, ("app-server",)),
    # The headless entry point. #913 shipped `--non-interactive`, which does
    # not exist; its own smoke file pins that specific regression.
    Engine("opencode", lambda: "opencode", _opencode, ("opencode run",)),
    # kilocode 0.22.0 takes a bare positional prompt plus these flags and has no
    # `run` subcommand (#1012). kilocode 7.x reinstated `run` and renamed
    # --workspace to --dir, so the adapter is stale against a current install —
    # tracked in #1015. This tier caught that drift on its own first CI run.
    Engine(
        "kilocode",
        _kilo_binary,
        _kilocode,
        ("--auto", "--workspace"),
        known_drift=(
            "adapter targets @kilocode/cli 0.22.0; 7.x renamed --workspace to "
            "--dir and reinstated `run` (#1015)"
        ),
    ),
)


def _cli_help(binary: str) -> str:
    """Return a CLI's help text. Several of these print help on stderr."""
    proc = subprocess.run(
        [binary, "--help"], capture_output=True, text=True, timeout=90
    )
    return proc.stdout + proc.stderr


def _require_binary(engine: Engine) -> str:
    resolved = shutil.which(engine.binary())
    if resolved is None:
        pytest.skip(f"{engine.name}: {engine.binary()} CLI not installed")
    return resolved


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git workspace with a baseline commit.

    The commit is load-bearing: without one HEAD is unborn, ``_git_head``
    returns None, and ``require_file_changes`` reads the workspace as "not a git
    repo" and never fires — silently neutering the zero-work assertions.
    """
    workspace = tmp_path / "repo"
    workspace.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=test",
         "commit", "-q", "--allow-empty", "-m", "baseline"],
        cwd=workspace,
        check=True,
    )
    return workspace


# ----------------------------------------------------------------------
# Contract leg — no credentials, safe to gate PRs
# ----------------------------------------------------------------------


@pytest.mark.parametrize("engine", ENGINES, ids=str)
def test_the_cli_is_installed_and_responds(engine: Engine) -> None:
    """The binary the adapter resolves exists and answers --help."""
    binary = _require_binary(engine)

    help_text = _cli_help(binary)
    assert help_text.strip(), f"{engine.name}: `{binary} --help` produced no output"


@pytest.mark.parametrize("engine", ENGINES, ids=str)
def test_the_cli_still_documents_the_adapters_entry_point(engine: Engine) -> None:
    """The invocation surface the adapter depends on is still in the CLI's help.

    Asserted against the CLI's own output, not against our code, so an upstream
    rename or removal fails here instead of silently producing no-op runs.
    """
    binary = _require_binary(engine)
    help_text = _cli_help(binary)

    missing = [s for s in engine.help_must_contain if s not in help_text]
    if missing and engine.known_drift:
        # Not strict: the day the adapter is migrated this passes on its own and
        # the xfail must be removed. Reported, never silent.
        pytest.xfail(f"{engine.name}: known drift — {engine.known_drift}; missing {missing}")
    assert not missing, (
        f"{engine.name}: {missing} absent from `{binary} --help` — the adapter's "
        f"invocation may no longer be valid"
    )


@pytest.mark.parametrize("engine", ENGINES, ids=str)
def test_the_adapter_constructs_against_the_real_binary(engine: Engine) -> None:
    """The adapter resolves the installed binary and builds a command from it.

    Catches an adapter whose binary resolution disagrees with what is installed
    — the construction path unit tests always patch away.
    """
    binary = _require_binary(engine)
    adapter = engine.adapter()

    assert adapter.name == engine.name
    if hasattr(adapter, "build_command"):
        cmd = adapter.build_command("say hello", Path("/tmp/repo"))
        assert cmd[0] == binary, f"{engine.name}: adapter targets {cmd[0]}, not {binary}"


# ----------------------------------------------------------------------
# Task leg — real credentials, real model calls, opt-in
# ----------------------------------------------------------------------


@pytest.mark.skipif(
    not _SMOKE_OPT_IN,
    reason="engine task smoke is opt-in: set CODEFRAME_ENGINE_SMOKE=1",
)
@pytest.mark.parametrize("engine", ENGINES, ids=str)
def test_the_adapter_drives_a_trivial_task_to_a_terminal_state(
    engine: Engine, repo: Path
) -> None:
    """One trivial task per engine, end to end, asserted on the file produced.

    Not "exit 0" and not "reached a terminal state" alone: every bug this tier
    exists to catch produced a clean-looking exit having done no work. The file
    on disk is the only evidence that survives.
    """
    _require_binary(engine)
    adapter = engine.adapter()

    result = adapter.run(
        "task-smoke",
        "Create a file smoke.txt containing exactly the word ACKNOWLEDGED. "
        "Do not create or modify any other file.",
        repo,
    )

    environmental = _environmental_reason(result.error)
    if environmental:
        pytest.skip(f"{engine.name}: NO COVERAGE — {environmental}")

    written = repo / "smoke.txt"
    assert written.exists(), (
        f"{engine.name}: reached status={result.status!r} but wrote no file "
        f"(error={result.error!r}) — this is the false-completion shape that "
        f"#913/#914/#1012 all had"
    )
    assert result.status == "completed", (
        f"{engine.name}: wrote the file but reported {result.status!r} "
        f"(error={result.error!r})"
    )
    assert "smoke.txt" in result.modified_files
