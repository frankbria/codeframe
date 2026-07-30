"""`cf review` fails loud instead of approving unexamined code (#910).

``SecurityScanner`` shelled out to bandit and, on ``FileNotFoundError``, logged a
warning and returned ``[]``. bandit was declared only under ``[dependency-groups]
dev``, so **no** ``pip install codeframe-ai`` ever had it. In every production
install the security leg produced nothing, ``scores`` stayed empty,
``overall_score`` fell through to ``100.0``, and the status became ``approved``
with nothing in ``ReviewResult`` saying the scan never ran.

The same ``100``/``approved`` came back when every requested file was
non-Python — a TypeScript-only change to a Next.js app was approved unexamined.
"""

import subprocess
from pathlib import Path

import pytest

from codeframe.core import review
from codeframe.core.workspace import create_or_load_workspace
from codeframe.lib.quality import security_scanner as scanner_module
from codeframe.lib.quality.security_scanner import ScannerUnavailableError, SecurityScanner

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    return create_or_load_workspace(repo)


@pytest.fixture
def bandit_missing(monkeypatch):
    """Exactly what a clean `pip install` used to look like."""
    real_run = subprocess.run

    def no_bandit(cmd, *args, **kwargs):
        if cmd and cmd[0] == "bandit":
            raise FileNotFoundError("bandit")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(scanner_module.subprocess, "run", no_bandit)


# ---------------------------------------------------------------------------
# bandit is installed by a normal install
# ---------------------------------------------------------------------------


def test_bandit_is_a_runtime_dependency():
    """It was under [dependency-groups] dev, so `pip install` never got it."""
    import tomllib

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())

    runtime = " ".join(data["project"]["dependencies"])
    assert "bandit" in runtime, "the security leg cannot run without bandit"


def test_bandit_is_actually_importable_here():
    """Guards the declaration above against being merely aspirational."""
    import shutil

    assert shutil.which("bandit"), "bandit declared but not present in this env"


# ---------------------------------------------------------------------------
# A missing scanner is loud
# ---------------------------------------------------------------------------


def test_the_scanner_raises_rather_than_returning_clean(tmp_path, bandit_missing):
    """`[]` made "no findings" indistinguishable from "no scan"."""
    target = tmp_path / "code.py"
    target.write_text("import os\n")

    with pytest.raises(ScannerUnavailableError):
        SecurityScanner(tmp_path).analyze_file(target)


def test_a_missing_scanner_is_not_approved_at_100(workspace, bandit_missing):
    """The headline bug: a clean install approved everything, unexamined."""
    target = workspace.repo_path / "app.py"
    target.write_text("x = 1\n")

    result = review.review_files(workspace, ["app.py"])

    assert result.status != "approved", f"{result.status} @ {result.overall_score}"
    assert result.overall_score != 100.0
    assert "security" in result.analyzers_unavailable


def test_a_missing_scanner_appears_in_the_findings(workspace, bandit_missing):
    """Every surface renders findings; an out-of-band flag would go unseen."""
    (workspace.repo_path / "app.py").write_text("x = 1\n")

    result = review.review_files(workspace, ["app.py"])

    tooling = [f for f in result.findings if f.category == "tooling"]
    assert tooling, "the unavailable scanner produced no finding"
    assert "bandit" in tooling[0].message
    assert tooling[0].severity == "high"


def test_the_scanner_is_reported_once_not_per_file(workspace, bandit_missing):
    """Ten files must not yield ten identical findings."""
    for i in range(3):
        (workspace.repo_path / f"m{i}.py").write_text("x = 1\n")

    result = review.review_files(workspace, ["m0.py", "m1.py", "m2.py"])

    tooling = [f for f in result.findings if f.category == "tooling"]
    assert len(tooling) == 1, f"{len(tooling)} duplicate tooling findings"


# ---------------------------------------------------------------------------
# Nothing analyzed is its own outcome
# ---------------------------------------------------------------------------


def test_a_typescript_only_change_is_not_approved(workspace):
    """The reported case: a Next.js change came back approved, unexamined."""
    (workspace.repo_path / "page.tsx").write_text("export default () => null;\n")

    result = review.review_files(workspace, ["page.tsx"])

    assert result.status == "not_analyzed", result.summary
    assert result.overall_score != 100.0
    assert "page.tsx" in result.files_skipped
    assert "No files were analyzed" in result.summary


def test_a_mixed_change_reports_what_was_skipped(workspace):
    """Python analyzed, TypeScript reported — not silently dropped."""
    (workspace.repo_path / "app.py").write_text("x = 1\n")
    (workspace.repo_path / "page.tsx").write_text("export default () => null;\n")

    result = review.review_files(workspace, ["app.py", "page.tsx"])

    assert result.status != "not_analyzed", "a Python file was analyzed"
    assert result.files_skipped == ["page.tsx"]
    assert "skipped" in result.summary


# ---------------------------------------------------------------------------
# The happy path still works
# ---------------------------------------------------------------------------


def test_clean_python_with_bandit_present_is_still_approved(workspace):
    """The fix must not make every review fail."""
    (workspace.repo_path / "clean.py").write_text("x = 1\n")

    result = review.review_files(workspace, ["clean.py"])

    assert result.status == "approved", f"{result.status}: {result.summary}"
    assert result.overall_score == 100.0
    assert not result.analyzers_unavailable


def test_a_real_finding_is_still_reported(workspace):
    """bandit genuinely runs — asserts the scan is wired, not just tolerated."""
    (workspace.repo_path / "risky.py").write_text(
        "import subprocess\n"
        "def go(cmd):\n"
        "    subprocess.run(cmd, shell=True)\n"
    )

    result = review.review_files(workspace, ["risky.py"])

    assert result.findings, "bandit reported nothing on a known-risky file"
    assert result.status != "not_analyzed"


# ---------------------------------------------------------------------------
# Sibling methods must not re-open the hole
# ---------------------------------------------------------------------------


def test_analyze_files_does_not_swallow_the_unavailable_error(tmp_path, bandit_missing):
    """Its generic `except Exception` would have silenced the new signal."""
    target = tmp_path / "code.py"
    target.write_text("x = 1\n")

    with pytest.raises(ScannerUnavailableError):
        SecurityScanner(tmp_path).analyze_files([target])


def test_calculate_score_does_not_return_a_perfect_score_when_unavailable(
    tmp_path, bandit_missing
):
    """The same 100-for-nothing-examined shape, one method over.

    These two have no production callers today; the guard is here so the next
    one does not inherit the bug.
    """
    target = tmp_path / "code.py"
    target.write_text("x = 1\n")

    with pytest.raises(ScannerUnavailableError):
        SecurityScanner(tmp_path).calculate_score([target])
