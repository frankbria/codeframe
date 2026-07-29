"""Gate dependency auto-install works in the state that triggers it (#908).

``_ensure_dependencies_installed`` fires exactly when ``requirements.txt``
exists and no venv does — and the old implementation ran ``uv pip install -r``
immediately, which errors in precisely that state::

    error: No virtual environment found; run `uv venv` to create an
    environment, or pass `--system` to install into a non-virtual environment

So the install could never succeed where it was triggered, ``run()`` returned
early with an ERROR, and *every* gate was blocked — including ruff and tsc,
which need no Python dependencies — for any pip-style repo. Every PROOF9 run
inherited that, since the runner calls ``gates.run`` per obligation.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from codeframe.core.gates import (
    GateStatus,
    _ensure_dependencies_installed,
    _install_python_requirements,
)

pytestmark = pytest.mark.v2


@pytest.fixture
def pip_repo(tmp_path):
    """The exact trigger state: requirements.txt present, no venv."""
    repo = tmp_path / "target-repo"
    repo.mkdir()
    # A dependency with no transitive deps, so the test does not depend on a
    # large download. Real install, no mocking.
    (repo / "requirements.txt").write_text("packaging\n")
    return repo


# ---------------------------------------------------------------------------
# The install must succeed in its own trigger state
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
def test_install_succeeds_when_no_venv_exists(pip_repo):
    ok, message = _install_python_requirements(pip_repo, pip_repo / "requirements.txt")

    assert ok, message
    assert (pip_repo / ".venv").is_dir(), "no venv was created"


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
def test_the_package_lands_in_the_target_venv(pip_repo):
    """Not merely 'the command exited 0' — the package must be importable there."""
    _install_python_requirements(pip_repo, pip_repo / "requirements.txt")

    venv_python = pip_repo / ".venv" / "bin" / "python"
    assert venv_python.exists()

    proc = subprocess.run(
        [str(venv_python), "-c", "import packaging; print(packaging.__file__)"],
        capture_output=True, text=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert str(pip_repo) in proc.stdout, "installed outside the target repo's venv"


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
def test_never_installs_into_codeframes_own_environment(pip_repo, monkeypatch):
    """`cf` run from an activated venv used to install into *that* venv.

    VIRTUAL_ENV is on the env allowlist, and the repo has no venv of its own at
    trigger time, so it was inherited straight from the parent process.
    """
    codeframe_venv = Path(sys.prefix)
    monkeypatch.setenv("VIRTUAL_ENV", str(codeframe_venv))

    ok, message = _install_python_requirements(pip_repo, pip_repo / "requirements.txt")

    assert ok, message
    venv_python = pip_repo / ".venv" / "bin" / "python"
    proc = subprocess.run(
        [str(venv_python), "-c", "import packaging; print(packaging.__file__)"],
        capture_output=True, text=True,
    )
    assert str(pip_repo) in proc.stdout, (
        f"installed into {proc.stdout.strip()} rather than the target repo's venv"
    )


# ---------------------------------------------------------------------------
# A failed install must not block the gates
# ---------------------------------------------------------------------------


def test_failed_install_still_runs_the_gates(tmp_path, monkeypatch):
    """ruff needs no Python dependencies; it must still run when install fails."""
    from codeframe.core import gates as gates_module
    from codeframe.core.workspace import create_or_load_workspace

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("packaging\n")
    (repo / "clean.py").write_text("x = 1\n")

    workspace = create_or_load_workspace(repo)

    monkeypatch.setattr(
        gates_module,
        "_ensure_dependencies_installed",
        lambda *a, **k: (False, "simulated install failure"),
    )

    result = gates_module.run(workspace, gates=["ruff"], verbose=False)

    names = {c.name for c in result.checks}
    assert "ruff" in names, f"gates did not run; only got {names}"

    dep_check = next(c for c in result.checks if c.name == "dependency-check")
    assert dep_check.status == GateStatus.SKIPPED
    assert "simulated install failure" in dep_check.output


def test_a_failed_install_alone_does_not_fail_the_run(tmp_path, monkeypatch):
    """SKIPPED does not fail the run; the gate that actually needs the deps does."""
    from codeframe.core import gates as gates_module
    from codeframe.core.workspace import create_or_load_workspace

    repo = tmp_path / "repo2"
    repo.mkdir()
    (repo / "requirements.txt").write_text("packaging\n")
    (repo / "clean.py").write_text("x = 1\n")

    workspace = create_or_load_workspace(repo)
    monkeypatch.setattr(
        gates_module,
        "_ensure_dependencies_installed",
        lambda *a, **k: (False, "simulated install failure"),
    )

    result = gates_module.run(workspace, gates=["ruff"], verbose=False)

    assert result.passed, [(c.name, c.status, c.output[:120]) for c in result.checks]


# ---------------------------------------------------------------------------
# The ordinary paths still behave
# ---------------------------------------------------------------------------


def test_existing_venv_is_left_alone(tmp_path):
    repo = tmp_path / "has-venv"
    (repo / ".venv").mkdir(parents=True)
    (repo / "requirements.txt").write_text("packaging\n")

    ok, message = _ensure_dependencies_installed(repo, auto_install=True)

    assert ok
    assert "already installed" in message


def test_auto_install_disabled_is_reported_not_attempted(pip_repo):
    ok, message = _ensure_dependencies_installed(pip_repo, auto_install=False)

    assert ok
    assert "auto-install disabled" in message
    assert not (pip_repo / ".venv").exists()


def test_dependency_note_never_displaces_the_gate_check(tmp_path, monkeypatch):
    """proof/runner.py reads `result.checks[0]` as *the* gate's check.

    A pre-flight entry at index 0 would be mistaken for the gate result and
    reported as `FAILED (SKIPPED)` for every enforced PROOF9 rule — a failure
    with nothing to do with the test it names.
    """
    from codeframe.core import gates as gates_module
    from codeframe.core.workspace import create_or_load_workspace

    repo = tmp_path / "repo3"
    repo.mkdir()
    (repo / "requirements.txt").write_text("packaging\n")
    (repo / "clean.py").write_text("x = 1\n")

    workspace = create_or_load_workspace(repo)
    monkeypatch.setattr(
        gates_module,
        "_ensure_dependencies_installed",
        lambda *a, **k: (False, "simulated install failure"),
    )

    result = gates_module.run(workspace, gates=["ruff"], verbose=False)

    assert result.checks[0].name == "ruff", (
        f"checks[0] is {result.checks[0].name!r}; the proof runner would read "
        "the dependency note as the gate result"
    )
    assert result.checks[-1].name == "dependency-check"


# ---------------------------------------------------------------------------
# Review findings
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
def test_a_failed_install_does_not_leave_a_venv_behind(tmp_path):
    """Otherwise the repo is 'already installed (venv exists)' forever.

    `uv venv` succeeds, the install fails on a transient network error, and the
    leftover `.venv` makes every later run skip the install — permanently, even
    once the network is back.
    """
    repo = tmp_path / "bad-requirements"
    repo.mkdir()
    # A requirement that cannot resolve, so the install fails after the venv
    # has already been created.
    (repo / "requirements.txt").write_text(
        "codeframe-nonexistent-package-908-test==9.9.9\n"
    )

    ok, message = _install_python_requirements(repo, repo / "requirements.txt")

    assert not ok
    assert not (repo / ".venv").exists(), (
        "the incomplete venv survived; the next run would report "
        "'already installed' and never retry"
    )

    # And the next check therefore still sees work to do.
    _, next_message = _ensure_dependencies_installed(repo, auto_install=False)
    assert "not installed" in next_message


def test_self_ignore_writes_the_ignore_file(tmp_path):
    """Deterministic check of the helper itself.

    The end-to-end test below cannot discriminate on this machine: `uv venv`
    writes `.venv/.gitignore` itself, and CPython does too since **3.13**. This
    project supports `>=3.11`, where neither is true — so the helper is tested
    directly rather than through an interpreter-dependent path.
    """
    from codeframe.core.gates import _self_ignore

    venv = tmp_path / ".venv"
    venv.mkdir()

    _self_ignore(venv)

    assert (venv / ".gitignore").read_text().strip() == "*"


def test_a_created_venv_is_ignored_by_git(tmp_path, monkeypatch):
    """`get_changed_scope` feeds untracked files into the PROOF9 scope.

    A property test: the venv must not be untracked, whether that comes from
    `_self_ignore`, `uv venv`, or CPython >= 3.13.
    """
    from codeframe.core import gates as gates_module

    repo = tmp_path / "git-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "requirements.txt").write_text("packaging\n")

    monkeypatch.setattr(gates_module.shutil, "which", lambda cmd: None)

    ok, message = gates_module._install_python_requirements(
        repo, repo / "requirements.txt"
    )
    assert ok, message

    untracked = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repo, capture_output=True, text=True,
    ).stdout
    assert ".venv" not in untracked, f"git still reports .venv as untracked:\n{untracked}"


def test_the_ignore_travels_with_the_venv_into_a_worktree(tmp_path):
    """CodeFRAME runs agents in linked worktrees, where `.git` is a *file*.

    A `.gitignore` inside the venv needs no git-directory resolution, so this
    works there unchanged — which an entry in `.git/info/exclude` would not.
    """
    from codeframe.core.gates import _self_ignore

    main = tmp_path / "main"
    main.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=main, check=True)
    (main / "seed.txt").write_text("seed\n")
    subprocess.run(["git", "add", "."], cwd=main, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed"],
        cwd=main, check=True,
    )

    linked = tmp_path / "linked"
    subprocess.run(
        ["git", "worktree", "add", "-q", str(linked), "-b", "wt"], cwd=main, check=True
    )
    assert (linked / ".git").is_file(), "expected a gitfile layout"

    venv = linked / ".venv"
    (venv / "lib").mkdir(parents=True)
    (venv / "lib" / "junk.py").write_text("x = 1\n")
    _self_ignore(venv)

    untracked = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=linked, capture_output=True, text=True,
    ).stdout
    assert ".venv" not in untracked, f"worktree still reports .venv:\n{untracked}"


def test_windows_style_venv_is_recognised(tmp_path):
    """build_agent_env only looked for `bin`, so a Windows venv was ignored and
    the target repo's pytest resolved from CodeFRAME's PATH instead."""
    from codeframe.core.agent_env import build_agent_env

    repo = tmp_path / "win-repo"
    scripts = repo / ".venv" / "Scripts"
    scripts.mkdir(parents=True)

    env = build_agent_env(repo)

    assert env["VIRTUAL_ENV"] == str(repo / ".venv")
    assert env["PATH"].startswith(str(scripts))


