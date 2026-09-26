"""A gate tool CodeFRAME ships must not fail just because it is off PATH (#1262).

After ``uv tool install codeframe-ai`` — the README install path — ruff and
bandit sit in the tool's own venv, not on PATH, and the user's project does not
depend on them. ``_run_ruff`` ran ``uv run ruff`` whenever uv existed, uv
answered "Failed to spawn: ruff", and the gate reported FAILED on perfectly
clean code. The ReactAgent's final verification could not fix that, so every
``cf work start --execute`` ended in a blocker. bandit had the same shape and
reported ERROR.

CI never saw it: ``uv run pytest`` puts CodeFRAME's ``.venv/bin`` (with ruff in
it) on PATH. So the real-process tests here rebuild the README's PATH — uv and
the system, no ruff — instead of mocking the spawn failure away.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import textwrap
from pathlib import Path

import pytest

from codeframe.core import gates as core_gates
from codeframe.core.gates import GateStatus

pytestmark = pytest.mark.v2

_SYSTEM_PATH = os.pathsep.join(["/usr/bin", "/bin"])
_UV = shutil.which("uv")


@pytest.fixture
def readme_install_path(tmp_path, monkeypatch):
    """PATH as `uv tool install codeframe-ai` leaves it: uv yes, ruff/bandit no."""
    if _UV is None:
        pytest.skip("uv not installed")
    bin_dir = tmp_path / "path-bin"
    bin_dir.mkdir()
    (bin_dir / "uv").symlink_to(_UV)
    path = os.pathsep.join([str(bin_dir), _SYSTEM_PATH])
    for tool in ("ruff", "bandit"):
        if shutil.which(tool, path=path):
            pytest.skip(f"{tool} is installed system-wide; cannot rebuild the README PATH")
    monkeypatch.setenv("PATH", path)
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)


@pytest.fixture
def repo(tmp_path) -> Path:
    """A user project that, like the cleanroom's, has no ruff dependency."""
    repo = tmp_path / "todo-api"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "todo-api"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    (repo / "app.py").write_text("VALUE = 1\n")
    return repo


def _hide_bundled_copy(monkeypatch):
    """Make CodeFRAME's own copy of every tool look uninstalled too."""
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a, **kw: None)


class TestRuffOffPath:
    def test_clean_code_passes(self, readme_install_path, repo):
        """The acceptance criterion: `Failed to spawn: ruff` is not a lint failure."""
        check = core_gates._run_ruff(repo)

        assert check.status == GateStatus.PASSED, check.output

    def test_lint_errors_still_fail(self, readme_install_path, repo):
        """The fallback has to actually lint, or the gate stops gating."""
        (repo / "app.py").write_text("import os\n")

        check = core_gates._run_ruff(repo)

        assert check.status == GateStatus.FAILED
        assert any(e.get("code") == "F401" for e in check.detailed_errors), check.output

    def test_unavailable_everywhere_is_skipped(self, readme_install_path, repo, monkeypatch):
        """No project copy and no bundled copy is unverifiable, not broken (#955)."""
        _hide_bundled_copy(monkeypatch)

        check = core_gates._run_ruff(repo)

        assert check.status == GateStatus.SKIPPED


class TestBanditOffPath:
    def test_the_scanner_still_runs(self, readme_install_path, repo):
        """bandit is a runtime dep (#910) so that SEC always has a scanner; off
        PATH it used to report ERROR on every README install."""
        (repo / "insecure.py").write_text(
            textwrap.dedent(
                """
                import os

                def run_it(user_input):
                    os.system("echo " + user_input)
                """
            ).lstrip()
        )

        check = core_gates._run_bandit(repo)

        assert check.status == GateStatus.FAILED, check.output
        assert "insecure.py" in check.output

    def test_unavailable_everywhere_is_skipped(self, readme_install_path, repo, monkeypatch):
        _hide_bundled_copy(monkeypatch)

        check = core_gates._run_bandit(repo)

        assert check.status == GateStatus.SKIPPED
