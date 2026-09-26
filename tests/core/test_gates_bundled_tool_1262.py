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
import subprocess
import sys
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
    # A low floor: build_agent_env sandboxes HOME, so uv can see only the
    # system interpreter, and it must not try to download one.
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "todo-api"\nversion = "0.1.0"\nrequires-python = ">=3.8"\n'
    )
    (repo / "app.py").write_text("VALUE = 1\n")
    return repo


_INSECURE = textwrap.dedent(
    """
    import os

    def run_it(user_input):
        os.system("echo " + user_input)
    """
).lstrip()


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

    def test_a_broken_config_fails_rather_than_skipping(self, readme_install_path, repo):
        """ruff's own error says "No such file or directory" and names ruff, which
        _tool_is_missing reads as a missing tool. Only a spawn failure may fall
        back; a ruff that ran and failed is the answer."""
        (repo / "ruff.toml").write_text('extend = "missing.toml"\n')

        check = core_gates._run_ruff(repo)

        assert check.status == GateStatus.FAILED, check.output

    def test_the_agent_sandbox_is_not_linted(self, readme_install_path, repo):
        """Outside git, ruff does not honour .codeframe's own .gitignore."""
        sandbox = repo / ".codeframe" / "agent-home"
        sandbox.mkdir(parents=True)
        (sandbox / "cached.py").write_text("import os\n")

        check = core_gates._run_ruff(repo)

        assert check.status == GateStatus.PASSED, check.output

    def test_the_gate_is_detected_without_uv_or_ruff_on_path(self, repo, monkeypatch, tmp_path):
        """A pipx install has neither on PATH, but CodeFRAME ships ruff."""
        empty = tmp_path / "empty-bin"
        empty.mkdir()
        monkeypatch.setenv("PATH", str(empty))

        assert "ruff" in core_gates._detect_available_gates(repo)


class TestPerFileLintOffPath:
    """The ReactAgent lints and autofixes each edit; off PATH both went SKIPPED."""

    def test_lint_reports_the_finding(self, readme_install_path, repo):
        target = repo / "app.py"
        target.write_text("import os\n")

        check = core_gates.run_lint_on_file(target, repo)

        assert check.status == GateStatus.FAILED, check.output
        assert [e["code"] for e in check.detailed_errors] == ["F401"]

    def test_a_broken_config_fails_rather_than_skipping(self, readme_install_path, repo):
        """Same rule as the gate: a ruff that ran and failed is not "missing"."""
        (repo / "ruff.toml").write_text('extend = "missing.toml"\n')

        check = core_gates.run_lint_on_file(repo / "app.py", repo)

        assert check.status == GateStatus.FAILED, check.output

    def test_autofix_with_a_broken_config_is_not_skipped(self, readme_install_path, repo):
        (repo / "ruff.toml").write_text('extend = "missing.toml"\n')

        check = core_gates.run_autofix_on_file(repo / "app.py", repo)

        assert check.status == GateStatus.ERROR, check.output

    def test_autofix_fixes_the_file(self, readme_install_path, repo):
        target = repo / "app.py"
        target.write_text("import os\nVALUE = 1\n")

        check = core_gates.run_autofix_on_file(target, repo)

        assert check.status == GateStatus.PASSED, check.output
        assert target.read_text() == "VALUE = 1\n"


class TestRuffOutputParsing:
    def test_the_full_format_is_parsed(self):
        """ruff >= 0.9's default. Without this a project pinning ruff and the
        gate got no detailed_errors, so self-correction saw only "Found 1 error."."""
        output = textwrap.dedent(
            """
            F401 [*] `os` imported but unused
             --> src/app.py:1:8
              |
            1 | import os
              |        ^^
              |
            help: Remove unused import: `os`

            E501 Line too long (100 > 88)
             --> src/app.py:3:89

            Found 2 errors.
            """
        )

        errors = core_gates._parse_ruff_errors(output)

        assert errors == [
            {"file": "src/app.py", "line": 1, "col": 8, "code": "F401",
             "message": "[*] `os` imported but unused"},
            {"file": "src/app.py", "line": 3, "col": 89, "code": "E501",
             "message": "Line too long (100 > 88)"},
        ]


class TestBanditOffPath:
    def test_the_scanner_still_runs(self, readme_install_path, repo):
        """bandit is a runtime dep (#910) so that SEC always has a scanner; off
        PATH it used to report ERROR on every README install."""
        (repo / "insecure.py").write_text(_INSECURE)

        check = core_gates._run_bandit(repo)

        assert check.status == GateStatus.FAILED, check.output
        assert "insecure.py" in check.output

    def test_unavailable_everywhere_is_skipped(self, readme_install_path, repo, monkeypatch):
        _hide_bundled_copy(monkeypatch)

        check = core_gates._run_bandit(repo)

        assert check.status == GateStatus.SKIPPED

    def test_installed_dependencies_are_not_scanned(self, readme_install_path, repo):
        """`uv run bandit` syncs the project into .venv before failing to spawn,
        so the fallback scanned third-party code and failed a clean project."""
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(repo / ".venv")], check=True)
        for vendored in (".venv/lib", ".tox/py/lib", ".codeframe/agent-home"):
            (repo / vendored).mkdir(parents=True, exist_ok=True)
            (repo / vendored / "dep.py").write_text(_INSECURE)

        check = core_gates._run_bandit(repo)

        assert check.status == GateStatus.PASSED, check.output


class TestReviewScannerOffPath:
    def test_cf_review_still_scans(self, readme_install_path, repo):
        """`cf review` checked shutil.which("bandit") and gave up on every README install."""
        from codeframe.lib.quality.security_scanner import SecurityScanner

        target = repo / "insecure.py"
        target.write_text(_INSECURE)

        findings = SecurityScanner(repo).analyze_file(target)

        assert findings, "bandit found nothing in a known-insecure file"


def test_a_clean_run_is_not_summarized_as_an_issue():
    """"All checks passed!" was counted as one issue line, so a PASSED gate's
    output read "1 issues found" — a contradiction on the success path."""
    assert core_gates._summarize_ruff_output("All checks passed!\n") == "All checks passed!"
