"""#1484 — a plain `cf proof run` re-checks satisfied requirements the diff touches.

A scoped run used to load only OPEN requirements (#923), so once a locked test
from `cf proof ratchet` was satisfied, a later regression was caught only by
`--full`. The pre-commit hook (#1470) runs a plain `cf proof run`, so the
ratchet's promise held only for a command nobody runs by default.

The rule: a scoped run also loads SATISFIED requirements whenever there is a
diff, and filters them through the same `intersects` as open ones. A clean
tree re-checks nothing satisfied (no diff, nothing in its scope); a failed
scope detection re-checks everything (fail closed, as for open ones). WAIVED
stays out of every run.
"""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core.proof import ledger
from codeframe.core.proof.capture import capture_requirement
from codeframe.core.proof.models import GateOutcome, ReqStatus, RequirementScope, Severity, Source, Waiver
from codeframe.core.proof.runner import EmptyReason, run_proof_with_diagnostics
from codeframe.core.workspace import create_or_load_workspace, get_workspace

pytestmark = [pytest.mark.v2, pytest.mark.timeout(300)]

runner = CliRunner()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True, capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    _git(repo, "init", "-q")
    (repo / "src" / "a.py").write_text("A = 1\n")
    (repo / "src" / "b.py").write_text("B = 1\n")
    return repo


def _satisfied(ws, where: str):
    req, _ = capture_requirement(
        ws, title=f"bug in {where}", description="d", where=where,
        severity=Severity.HIGH, source=Source.QA,
    )
    ledger.mark_satisfied(ws, req)
    return ledger.get_requirement(ws, req.id)


def _commit(repo: Path) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "c")


class TestScopedRunRechecksSatisfied:
    def test_a_satisfied_requirement_in_the_diff_is_rechecked_and_reopened(self, repo):
        ws = create_or_load_workspace(repo)
        req = _satisfied(ws, "src/a.py")
        _commit(repo)
        (repo / "src" / "a.py").write_text("A = 2\n")

        with patch("codeframe.core.proof.runner._run_gate", return_value=(GateOutcome.FAILED, "boom")):
            results, _ = run_proof_with_diagnostics(ws)

        assert req.id in results
        assert ledger.get_requirement(ws, req.id).status == ReqStatus.OPEN

    def test_a_satisfied_requirement_outside_the_diff_is_not_run(self, repo):
        ws = create_or_load_workspace(repo)
        touched = _satisfied(ws, "src/a.py")
        untouched = _satisfied(ws, "src/b.py")
        _commit(repo)
        (repo / "src" / "a.py").write_text("A = 2\n")

        with patch("codeframe.core.proof.runner._run_gate", return_value=(GateOutcome.PASSED, "ok")) as gate:
            results, diagnostics = run_proof_with_diagnostics(ws)

        assert set(results) == {touched.id}
        assert untouched.id in diagnostics.scope_skipped
        assert gate.call_count == len(touched.obligations)
        assert ledger.get_requirement(ws, untouched.id).status == ReqStatus.SATISFIED

    def test_a_clean_tree_rechecks_nothing_satisfied(self, repo):
        ws = create_or_load_workspace(repo)
        req = _satisfied(ws, "src/a.py")
        _commit(repo)

        with patch("codeframe.core.proof.runner._run_gate") as gate:
            results, diagnostics = run_proof_with_diagnostics(ws)

        assert results == {}
        gate.assert_not_called()
        assert diagnostics.reason is EmptyReason.EXCLUDED_BY_STATUS
        assert ledger.get_requirement(ws, req.id).status == ReqStatus.SATISFIED

    def test_a_failed_scope_detection_rechecks_satisfied_too(self, repo):
        """None means detection failed: fail closed, as for open requirements."""
        ws = create_or_load_workspace(repo)
        req = _satisfied(ws, "src/a.py")

        with patch("codeframe.core.proof.runner.get_changed_scope", return_value=None), \
                patch("codeframe.core.proof.runner._run_gate", return_value=(GateOutcome.PASSED, "ok")):
            results, _ = run_proof_with_diagnostics(ws)

        assert req.id in results

    def test_a_waived_requirement_in_the_diff_stays_out(self, repo):
        ws = create_or_load_workspace(repo)
        req = _satisfied(ws, "src/a.py")
        ledger.waive_requirement(ws, req.id, Waiver(reason="accepted", approved_by="t"))
        _commit(repo)
        (repo / "src" / "a.py").write_text("A = 2\n")

        with patch("codeframe.core.proof.runner._run_gate") as gate:
            results, diagnostics = run_proof_with_diagnostics(ws)

        assert results == {}
        gate.assert_not_called()
        assert diagnostics.reason is EmptyReason.EXCLUDED_BY_STATUS

    def test_satisfied_but_out_of_scope_reports_excluded_by_scope(self, repo):
        ws = create_or_load_workspace(repo)
        req = _satisfied(ws, "src/b.py")
        _commit(repo)
        (repo / "src" / "a.py").write_text("A = 2\n")

        with patch("codeframe.core.proof.runner._run_gate") as gate:
            results, diagnostics = run_proof_with_diagnostics(ws)

        assert results == {}
        gate.assert_not_called()
        assert diagnostics.reason is EmptyReason.EXCLUDED_BY_SCOPE
        assert diagnostics.scope_skipped == [req.id]


CALC = "def add(a, b):\n    return a + b\n"
TESTS = "from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"


def test_the_issue_repro_a_ratchet_lock_catches_a_regression_without_full(tmp_path):
    """#1484's verified steps, with real pytest: ratchet, run --full (all
    satisfied), break add() and commit nothing yet, plain run — it now fails."""
    repo = tmp_path / "calc"
    (repo / "tests").mkdir(parents=True)
    _git(repo, "init", "-q")
    (repo / "pytest.ini").write_text("[pytest]\npythonpath = .\n")
    (repo / "calc.py").write_text(CALC)
    (repo / "tests" / "test_calc.py").write_text(TESTS)

    assert runner.invoke(app, ["proof", "ratchet", "-w", str(repo)]).exit_code == 0
    _commit(repo)
    first = runner.invoke(app, ["proof", "run", "--full", "-w", str(repo)])
    assert first.exit_code == 0, first.output

    # A different length too: same size and mtime second would reuse the .pyc.
    (repo / "calc.py").write_text(CALC.replace("return a + b", "return a + b + 1"))
    result = runner.invoke(app, ["proof", "run", "-w", str(repo)])

    assert result.exit_code == 1, result.output
    [req] = ledger.list_requirements(get_workspace(repo))
    assert req.status == ReqStatus.OPEN


def test_the_ratchet_no_longer_says_full_is_needed_to_recheck(tmp_path):
    repo = tmp_path / "calc"
    (repo / "tests").mkdir(parents=True)
    _git(repo, "init", "-q")
    (repo / "pytest.ini").write_text("[pytest]\npythonpath = .\n")
    (repo / "calc.py").write_text(CALC)
    (repo / "tests" / "test_calc.py").write_text(TESTS)

    result = runner.invoke(app, ["proof", "ratchet", "-w", str(repo)])

    text = " ".join(result.output.split())
    assert result.exit_code == 0, result.output
    assert "skips satisfied requirements" not in text
    assert "cf proof run" in text


def test_requirements_for_run_takes_the_changed_scope():
    """The selection rule in one place: satisfied joins when there is a diff."""
    from codeframe.core.proof.runner import _wants_satisfied

    assert _wants_satisfied(full=True, changed_scope=None)
    assert _wants_satisfied(full=False, changed_scope=None)
    assert _wants_satisfied(full=False, changed_scope=RequirementScope(files=["x.py"]))
    assert not _wants_satisfied(full=False, changed_scope=RequirementScope())
