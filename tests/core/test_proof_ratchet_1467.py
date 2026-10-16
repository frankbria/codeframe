"""#1467 — `cf proof ratchet` locks currently-passing tests in as obligations.

A fresh install has an empty ledger, so `cf proof run` exits 2 and nothing
visibly happens. The ratchet turns the tests that pass today into
requirements, so the ledger has something to enforce from minute one —
without inventing a single criterion.

Every test here runs the fixture project's real test suite, so it lives with
the other real-pytest proof tests in tests/core rather than tests/cli: the
Unlocked Resolution job runs tests/cli in an env whose interpreter the fixture
projects cannot reach, and there the ratchet correctly reports "pytest is not
in the project's dependencies".
"""

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core.proof import ledger
from codeframe.core.proof.capture import capture_requirement
from codeframe.core.proof.models import Gate, ReqStatus, Severity, Source
from codeframe.core.workspace import CODEFRAME_DIR, create_or_load_workspace, get_workspace

pytestmark = [pytest.mark.v2, pytest.mark.timeout(300)]

runner = CliRunner()

LOCKED = "Nothing that passes today can silently stop passing."

CALC = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"
OTHER = "def mul(a, b):\n    return a * b\n"
TESTS = '''\
import pytest

from calc import add, sub


def test_add():
    assert add(1, 2) == 3


def test_sub():
    assert sub(3, 1) == 2


def test_broken():
    assert False


@pytest.mark.skip(reason="not yet")
def test_skipped():
    assert True


def testCamel():
    assert True
'''


def _project(repo: Path, files: dict[str, str], ini: str = "pythonpath = .") -> Path:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "pytest.ini").write_text(f"[pytest]\n{ini}\n", encoding="utf-8")
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text, encoding="utf-8")
    return repo


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return _project(
        tmp_path / "repo",
        {"calc.py": CALC, "other.py": OTHER, "tests/test_calc.py": TESTS},
    )


def _ratchet(repo: Path, *args: str):
    result = runner.invoke(app, ["proof", "ratchet", "-w", str(repo), *args])
    # Rich wraps at the terminal width; compare the words, not the line breaks.
    result.text = " ".join(result.output.split())
    return result


def _ratcheted(repo: Path) -> dict[str, "ledger.Requirement"]:
    return {
        r.evidence_rules[0].test_id: r
        for r in ledger.list_requirements(get_workspace(repo))
        if r.source == Source.RATCHET
    }


class TestLockIn:
    def test_one_obligation_per_passing_test_scoped_to_the_files_it_covers(self, repo):
        result = _ratchet(repo)

        assert result.exit_code == 0, result.output
        assert "Locked in 2 passing tests as obligations." in result.text
        assert LOCKED in result.text

        reqs = _ratcheted(repo)
        assert set(reqs) == {"test_add", "test_sub"}
        for req in reqs.values():
            assert req.status == ReqStatus.OPEN
            assert [o.gate for o in req.obligations] == [Gate.UNIT]
            assert [(r.gate, r.must_pass) for r in req.evidence_rules] == [(Gate.UNIT, True)]
            assert "calc.py" in req.scope.files
            assert "tests/test_calc.py" in req.scope.files
            # Covered files only: nothing imports other.py.
            assert "other.py" not in req.scope.files

    def test_failing_skipped_and_unenforceable_tests_are_not_locked_and_are_reported(self, repo):
        result = _ratchet(repo)

        assert result.exit_code == 0, result.output
        assert "test_broken" not in _ratcheted(repo)
        assert "test_skipped" not in _ratcheted(repo)
        # The runner only enforces `test_`-prefixed names; locking `testCamel`
        # would create an obligation that fails forever.
        assert "testCamel" not in _ratcheted(repo)
        assert "1 failed" in result.output
        assert "1 skipped" in result.output
        assert "testCamel" in result.output

    def test_a_name_that_fails_in_another_file_is_not_locked(self, tmp_path):
        """The runner judges a rule by every case with that name; locking it
        here would be an obligation that fails on its first run."""
        repo = _project(tmp_path / "repo", {
            "tests/test_a.py": "def test_same():\n    assert True\n\n\ndef test_only_a():\n    assert True\n",
            "tests/test_b.py": "def test_same():\n    assert False\n",
        })

        result = _ratchet(repo)

        assert result.exit_code == 0, result.output
        assert set(_ratcheted(repo)) == {"test_only_a"}

    def test_the_workspace_is_created_on_first_use(self, repo):
        assert not (repo / CODEFRAME_DIR).exists()

        result = _ratchet(repo)

        assert result.exit_code == 0, result.output
        assert "Created .codeframe/ in this repository." in result.output

    def test_path_glob_limits_which_tests_are_locked(self, tmp_path):
        repo = _project(tmp_path / "repo", {
            "calc.py": CALC,
            "tests/unit/test_one.py": "def test_one():\n    assert True\n",
            "tests/slow/test_two.py": "def test_two():\n    assert True\n",
        })

        result = _ratchet(repo, "--path", "tests/unit/*.py")

        assert result.exit_code == 0, result.output
        assert set(_ratcheted(repo)) == {"test_one"}

    def test_path_does_not_lock_a_name_that_fails_outside_it(self, tmp_path):
        """The runner judges a name over the whole suite, so a name that also
        fails outside --path would be an obligation failing on its first run."""
        repo = _project(tmp_path / "repo", {
            "tests/unit/test_u.py": "def test_parse():\n    assert True\n\n\ndef test_u():\n    assert True\n",
            "tests/int/test_i.py": "def test_parse():\n    assert False\n",
        })

        result = _ratchet(repo, "--path", "tests/unit/*")

        assert result.exit_code == 0, result.output
        assert set(_ratcheted(repo)) == {"test_u"}

    def test_path_cannot_reach_outside_the_repository(self, tmp_path):
        _project(tmp_path / "other", {"tests/test_o.py": "def test_o():\n    assert True\n"})
        repo = _project(tmp_path / "repo", {"calc.py": CALC, "tests/test_calc.py": TESTS})

        result = _ratchet(repo, "--path", "../other/tests/*")

        assert result.exit_code == 2, result.output
        assert "No tests found" in result.text
        assert "test_o" not in result.output

    def test_relative_coverage_paths_resolve_against_the_repository(self, tmp_path):
        """`relative_files = True` stores repo-relative paths; resolving them
        against cf's own cwd dropped every source file from the scope."""
        repo = _project(tmp_path / "repo", {
            "calc.py": CALC, "tests/test_calc.py": TESTS,
            ".coveragerc": "[run]\nrelative_files = True\n",
        })

        result = _ratchet(repo)

        assert result.exit_code == 0, result.output
        assert "calc.py" in _ratcheted(repo)["test_add"].scope.files

    def test_without_per_test_coverage_each_obligation_covers_the_whole_repo(self, tmp_path):
        """No pytest-cov in the project: scope must fail closed, never to a
        guess that lets a change to the code under test go unexamined."""
        repo = _project(
            tmp_path / "repo",
            {"calc.py": CALC, "tests/test_calc.py": TESTS},
            ini="pythonpath = .\naddopts = -p no:pytest_cov",
        )

        result = _ratchet(repo)

        assert result.exit_code == 0, result.output
        assert "pytest-cov" in result.output
        reqs = _ratcheted(repo)
        assert set(reqs) == {"test_add", "test_sub"}
        assert all(r.scope.files == ["."] for r in reqs.values())


class TestDryRun:
    def test_dry_run_in_a_fresh_repo_creates_nothing(self, repo):
        result = _ratchet(repo, "--dry-run")

        assert result.exit_code == 0, result.output
        assert "Would lock in 2 passing tests" in result.text
        assert "test_add" in result.output
        assert not (repo / CODEFRAME_DIR).exists()
        assert not (repo / ".pytest_cache").exists()

    def test_dry_run_leaves_an_existing_ledger_unchanged(self, repo):
        ws = create_or_load_workspace(repo)
        ledger.init_proof_tables(ws)

        result = _ratchet(repo, "--dry-run")

        assert result.exit_code == 0, result.output
        assert ledger.list_requirements(ws) == []


class TestRerun:
    def test_a_second_run_creates_no_duplicates(self, repo):
        assert _ratchet(repo).exit_code == 0
        before = ledger.list_requirements(get_workspace(repo))

        second = _ratchet(repo)

        assert second.exit_code == 0, second.output
        assert len(ledger.list_requirements(get_workspace(repo))) == len(before) == 2
        assert "already locked" in second.output

    def test_a_newly_passing_test_is_added_on_rerun(self, repo):
        assert _ratchet(repo).exit_code == 0
        tests = repo / "tests" / "test_calc.py"
        tests.write_text(tests.read_text().replace("assert False", "assert True"))

        second = _ratchet(repo)

        assert second.exit_code == 0, second.output
        assert "Locked in 1 passing test as obligations." in second.text
        assert set(_ratcheted(repo)) == {"test_add", "test_sub", "test_broken"}


class TestNothingToLock:
    def test_no_tests_exits_non_zero_and_creates_no_workspace(self, tmp_path):
        repo = _project(tmp_path / "repo", {"calc.py": CALC})

        result = _ratchet(repo)

        assert result.exit_code == 2, result.output
        assert "No tests found" in result.output
        assert "Locked in" not in result.output
        assert not (repo / CODEFRAME_DIR).exists()

    def test_a_path_that_matches_nothing_exits_non_zero(self, repo):
        result = _ratchet(repo, "--path", "nope/*.py")

        assert result.exit_code == 2, result.output
        assert "No tests found" in result.output

    def test_a_suite_that_cannot_run_exits_non_zero(self, tmp_path):
        repo = _project(tmp_path / "repo", {
            "tests/test_ok.py": "def test_ok():\n    assert True\n",
            "tests/test_bad.py": "def test_bad(:\n",
        })

        result = _ratchet(repo)

        assert result.exit_code == 1, result.output
        assert "could not run" in result.output
        assert "Locked in" not in result.output
        assert not (repo / CODEFRAME_DIR).exists()

    def test_a_suite_where_nothing_passes_exits_non_zero(self, tmp_path):
        repo = _project(tmp_path / "repo", {
            "tests/test_red.py": "def test_red():\n    assert False\n",
        })

        result = _ratchet(repo)

        assert result.exit_code == 2, result.output
        assert "No passing tests eligible to lock in" in result.text
        assert "Locked in" not in result.output


class TestEnforcement:
    def test_proof_run_exercises_the_locked_tests_and_fails_on_a_regression(self, repo):
        assert _ratchet(repo).exit_code == 0
        # A different length too: same size and mtime second would reuse the .pyc.
        (repo / "calc.py").write_text(CALC.replace("return a + b", "return a + b + 1"))

        result = runner.invoke(app, ["proof", "run", "-w", str(repo)])

        assert result.exit_code == 1, result.output
        reqs = _ratcheted(repo)
        assert reqs["test_add"].status == ReqStatus.OPEN
        assert reqs["test_add"].obligations[0].status == "failed"
        assert reqs["test_sub"].status == ReqStatus.SATISFIED

    def test_a_regression_after_the_first_proof_run_fails_a_full_run(self, repo):
        """Once satisfied, a locked test is re-verified by --full (#923), so
        that is the command the ratchet points at."""
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
             "commit", "-qm", "init"], check=True,
        )
        ratchet = _ratchet(repo)
        assert "cf proof run --full" in ratchet.text
        first = runner.invoke(app, ["proof", "run", "--full", "-w", str(repo)])
        assert first.exit_code == 0, first.output
        assert _ratcheted(repo)["test_add"].status == ReqStatus.SATISFIED

        (repo / "calc.py").write_text(CALC.replace("return a + b", "return a + b + 1"))
        result = runner.invoke(app, ["proof", "run", "--full", "-w", str(repo)])

        assert result.exit_code == 1, result.output
        assert _ratcheted(repo)["test_add"].status == ReqStatus.OPEN


class TestSourceIsReserved:
    def test_capture_refuses_the_ratchet_source(self, repo):
        ws = create_or_load_workspace(repo)

        with pytest.raises(ValueError, match="ratchet"):
            capture_requirement(
                ws, title="t", description="d", where="calc.py",
                severity=Severity.LOW, source=Source.RATCHET,
            )
        assert ledger.list_requirements(ws) == []

    def test_cli_capture_refuses_the_ratchet_source(self, repo):
        result = runner.invoke(app, [
            "proof", "capture", "-w", str(repo), "--title", "t", "--description", "d",
            "--where", "calc.py", "--severity", "low", "--source", "ratchet",
        ])

        assert result.exit_code == 1, result.output
        assert "ratchet" in result.output
