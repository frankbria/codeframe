"""Direct unit tests for codeframe.core.review.

review.py is pure-filesystem (no git/DB): it runs the complexity / security /
OWASP analyzers over a file list and aggregates findings into a score+status.
We patch the three analyzers so tests are deterministic and never shell out to
``bandit``. The score/severity threshold helpers are tested in isolation.

Issue #654 (P6.8.1): test coverage hardening for untested core modules.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from codeframe.core import review as review_mod
from codeframe.core.review import (
    ReviewFinding,
    ReviewResult,
    _determine_status,
    _severity_from_score,
    review_files,
    review_task,
    get_review_summary,
)
from codeframe.core.workspace import Workspace
from codeframe.lib.quality.complexity_analyzer import ComplexityAnalyzer
from codeframe.lib.quality.security_scanner import SecurityScanner
from codeframe.lib.quality.owasp_patterns import OWASPPatterns


pytestmark = pytest.mark.v2


class _Finding:
    """Minimal stand-in for an analyzer finding (review.py reads 5 attrs)."""

    def __init__(self, severity, category="complexity", message="issue",
                 line_number=1, suggestion=None):
        self.severity = severity
        self.category = category
        self.message = message
        self.line_number = line_number
        self.suggestion = suggestion


@pytest.fixture
def workspace(tmp_path) -> Workspace:
    repo = tmp_path / "repo"
    repo.mkdir()
    return Workspace(
        id="ws-test",
        repo_path=repo,
        state_dir=repo / ".codeframe",
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture(autouse=True)
def quiet_heavy_analyzers(monkeypatch):
    """Silence the analyzers that shell out / are heavy (bandit, OWASP regex).

    The in-process radon-based ComplexityAnalyzer is left REAL so the default
    path exercises a real analyzer (it returns [] for trivial files); individual
    tests override it via monkeypatch when they need controlled findings.
    """
    monkeypatch.setattr(SecurityScanner, "analyze_file", lambda self, p: [])
    monkeypatch.setattr(OWASPPatterns, "check_file", lambda self, p: [])


def _write_py(workspace: Workspace, name: str = "mod.py") -> str:
    (workspace.repo_path / name).write_text("def f():\n    return 1\n")
    return name


# --- threshold helpers ------------------------------------------------------


class TestDetermineStatus:
    @pytest.mark.parametrize(
        "score,expected",
        [
            (100.0, "approved"),
            (70.0, "approved"),
            (69.9, "changes_requested"),
            (50.0, "changes_requested"),
            (49.9, "rejected"),
            (0.0, "rejected"),
        ],
    )
    def test_thresholds(self, score, expected):
        assert _determine_status(score) == expected


class TestSeverityFromScore:
    @pytest.mark.parametrize(
        "score,expected",
        [
            (10, "critical"),
            (29.9, "critical"),
            (30, "high"),
            (49.9, "high"),
            (50, "medium"),
            (69.9, "medium"),
            (70, "low"),
            (89.9, "low"),
            (90, "info"),
            (100, "info"),
        ],
    )
    def test_thresholds(self, score, expected):
        assert _severity_from_score(score) == expected


# --- review_files -----------------------------------------------------------


class TestReviewFiles:
    def test_no_findings_is_perfect_score(self, workspace):
        name = _write_py(workspace)
        result = review_files(workspace, [name])

        assert isinstance(result, ReviewResult)
        assert result.overall_score == 100.0
        assert result.status == "approved"
        assert result.findings == []
        assert "No issues found" in result.summary

    def test_findings_lower_score_and_status(self, workspace, monkeypatch):
        name = _write_py(workspace)
        monkeypatch.setattr(
            ComplexityAnalyzer,
            "analyze_file",
            lambda self, p: [_Finding("high", message="too complex")],
        )
        result = review_files(workspace, [name])

        assert len(result.findings) == 1
        assert result.findings[0].severity == "high"
        assert result.findings[0].file_path == name
        # high → score 40 → rejected (< 50)
        assert result.overall_score == 40.0
        assert result.status == "rejected"
        assert "1 high severity" in result.summary

    def test_averages_multiple_findings(self, workspace, monkeypatch):
        name = _write_py(workspace)
        monkeypatch.setattr(
            ComplexityAnalyzer,
            "analyze_file",
            lambda self, p: [_Finding("low"), _Finding("info")],
        )
        result = review_files(workspace, [name])
        # low=80, info=95 → average 87.5 → approved
        assert result.overall_score == 87.5
        assert result.status == "approved"

    def test_non_python_file_is_skipped(self, workspace):
        (workspace.repo_path / "notes.txt").write_text("not code")
        result = review_files(workspace, ["notes.txt"])
        assert result.findings == []
        assert result.overall_score == 100.0

    def test_missing_file_is_skipped(self, workspace):
        result = review_files(workspace, ["ghost.py"])
        assert result.findings == []
        assert result.overall_score == 100.0

    def test_analyzer_exception_is_caught(self, workspace, monkeypatch):
        name = _write_py(workspace)

        def boom(self, p):
            raise RuntimeError("analyzer exploded")

        monkeypatch.setattr(ComplexityAnalyzer, "analyze_file", boom)
        # Should not propagate; other analyzers still run → no findings.
        result = review_files(workspace, [name])
        assert isinstance(result, ReviewResult)
        assert result.findings == []

    def test_real_complexity_analyzer_integration(self, workspace):
        """Smoke test against the REAL ComplexityAnalyzer (no mock) to lock the
        finding attribute contract review.py depends on (category/severity/
        line_number/message/suggestion)."""
        complex_src = "def m(a, b, c, d, e):\n" + "".join(
            f"    if a == {i}:\n        return b if c else d\n" for i in range(15)
        ) + "    return e\n"
        (workspace.repo_path / "complex.py").write_text(complex_src)

        result = review_files(workspace, ["complex.py"])

        assert result.findings, "real analyzer should flag a high-complexity function"
        flagged = result.findings[0]
        assert flagged.category == "complexity"
        assert flagged.file_path == "complex.py"
        assert flagged.severity in {"critical", "high", "medium", "low", "info"}
        # A real complexity finding lowers the score below perfect.
        assert result.overall_score < 100.0


# --- review_task ------------------------------------------------------------


class TestReviewTask:
    def test_delegates_to_review_files(self, workspace, monkeypatch):
        captured = {}

        def fake_review_files(ws, files):
            captured["ws"] = ws
            captured["files"] = files
            return ReviewResult("approved", 100.0, [], "ok")

        monkeypatch.setattr(review_mod, "review_files", fake_review_files)
        result = review_task(workspace, task_id="T-1", files_modified=["a.py"])

        assert result.status == "approved"
        assert captured["ws"] is workspace
        assert captured["files"] == ["a.py"]


class TestWorkspaceContainment:
    """Issue #899 / P0.5 — caller-supplied paths must not escape the workspace.

    ``review_files`` joined caller input straight onto ``repo_path`` with only an
    existence + ``.py`` suffix check. An absolute path replaces the base and
    ``../`` walks out, so any authenticated principal could scan any ``.py`` file
    the server user can read and get back existence plus per-line findings —
    including the literal secret strings bandit quotes back. Cross-tenant read in
    hosted mode.

    Note the assertions below check *which path the analyzer was handed*, not
    merely that the result had no findings: the autouse fixture stubs the
    scanners out, so a findings-empty assertion would pass with or without the
    guard. What must be true is that an out-of-workspace path never reaches an
    analyzer at all.
    """

    @pytest.fixture
    def outsider(self, tmp_path):
        """A readable .py file that lives OUTSIDE the workspace."""
        secret = tmp_path / "outside.py"
        secret.write_text('API_KEY = "super-secret-value"\n')
        return secret

    @pytest.fixture
    def analyzed(self, monkeypatch):
        """Record every path handed to an analyzer, and report one finding for
        each so an escape would also be visible in the result."""
        seen: list = []

        def _record(self, path):
            seen.append(Path(path))
            return [_Finding("high")]

        monkeypatch.setattr(ComplexityAnalyzer, "analyze_file", _record)
        return seen

    @pytest.mark.parametrize(
        "attack",
        [
            "../outside.py",
            "sub/../../outside.py",
            "./../outside.py",
            "../../../../../../etc/passwd.py",
        ],
    )
    def test_traversal_never_reaches_an_analyzer(
        self, workspace, outsider, analyzed, attack
    ):
        result = review_files(workspace, [attack])

        assert analyzed == [], f"analyzer was handed {analyzed}"
        assert result.findings == []

    def test_absolute_path_never_reaches_an_analyzer(
        self, workspace, outsider, analyzed
    ):
        """An absolute path silently replaces the base in ``project_path / p``."""
        result = review_files(workspace, [str(outsider)])

        assert analyzed == [], f"analyzer was handed {analyzed}"
        assert result.findings == []

    def test_symlink_out_of_the_workspace_is_rejected(
        self, workspace, outsider, analyzed
    ):
        """``resolve()`` follows symlinks, so a planted link inside the workspace
        cannot smuggle an outside file past the check."""
        (workspace.repo_path / "link.py").symlink_to(outsider)

        review_files(workspace, ["link.py"])

        assert analyzed == [], f"analyzer was handed {analyzed}"

    def test_traversal_does_not_leak_existence(self, workspace, tmp_path, analyzed):
        """The guard must run BEFORE the existence probe, so a real outside file
        and a missing one are indistinguishable to the caller."""
        (tmp_path / "real.py").write_text("x = 1\n")

        real = review_files(workspace, ["../real.py"])
        absent = review_files(workspace, ["../definitely-absent.py"])

        assert analyzed == []
        assert (real.status, real.overall_score, real.findings) == (
            absent.status,
            absent.overall_score,
            absent.findings,
        )

    def test_legitimate_relative_paths_still_work(self, workspace, analyzed):
        nested = workspace.repo_path / "pkg"
        nested.mkdir()
        (nested / "mod.py").write_text("def f():\n    return 1\n")

        result = review_files(workspace, ["pkg/mod.py"])

        assert analyzed == [(workspace.repo_path / "pkg" / "mod.py").resolve()]
        assert len(result.findings) == 1
        assert result.findings[0].file_path == "pkg/mod.py"

    def test_a_good_path_is_still_reviewed_alongside_a_rejected_one(
        self, workspace, outsider, analyzed
    ):
        """One bad entry must not abort the whole request."""
        (workspace.repo_path / "ok.py").write_text("def f():\n    return 1\n")

        result = review_files(workspace, [str(outsider), "ok.py"])

        assert analyzed == [(workspace.repo_path / "ok.py").resolve()]
        assert len(result.findings) == 1

    def test_review_task_is_covered_by_the_same_guard(
        self, workspace, outsider, analyzed
    ):
        """review_task delegates to review_files, so it inherits the guard —
        pinned because the issue names it as a shared code path."""
        review_task(workspace, task_id="T-1", files_modified=[str(outsider)])

        assert analyzed == [], f"analyzer was handed {analyzed}"


# --- get_review_summary -----------------------------------------------------


class TestGetReviewSummary:
    def test_counts_and_blocking_flag(self):
        findings = [
            ReviewFinding("security", "critical", "m", "a.py"),
            ReviewFinding("complexity", "high", "m", "a.py"),
            ReviewFinding("style", "low", "m", "b.py"),
        ]
        result = ReviewResult("rejected", 40.0, findings, "summary")
        summary = get_review_summary(result)

        assert summary["status"] == "rejected"
        assert summary["overall_score"] == 40.0
        assert summary["total_findings"] == 3
        assert summary["severity_counts"]["critical"] == 1
        assert summary["severity_counts"]["high"] == 1
        assert summary["severity_counts"]["low"] == 1
        assert summary["severity_counts"]["medium"] == 0
        assert summary["has_blocking_issues"] is True

    def test_no_blocking_issues_when_only_low_info(self):
        findings = [
            ReviewFinding("style", "low", "m", "a.py"),
            ReviewFinding("style", "info", "m", "a.py"),
        ]
        summary = get_review_summary(ReviewResult("approved", 90.0, findings, "s"))
        assert summary["has_blocking_issues"] is False

    def test_empty_findings(self):
        summary = get_review_summary(ReviewResult("approved", 100.0, [], "clean"))
        assert summary["total_findings"] == 0
        assert summary["has_blocking_issues"] is False
        assert all(v == 0 for v in summary["severity_counts"].values())
