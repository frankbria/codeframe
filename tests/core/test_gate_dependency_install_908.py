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
