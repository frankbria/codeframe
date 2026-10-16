"""#1488 — `cf proof ratchet --json`.

Runs the fixture project's real pytest suite, so it lives in tests/core with
the other ratchet tests (see test_proof_ratchet_1467.py for why).
"""

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core.workspace import CODEFRAME_DIR

pytestmark = [pytest.mark.v2, pytest.mark.timeout(300)]

runner = CliRunner()

TESTS = """from calc import add


def test_add():
    assert add(1, 2) == 3


def test_broken():
    assert add(1, 1) == 3
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "pytest.ini").write_text("[pytest]\npythonpath = .\n", encoding="utf-8")
    (repo / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (repo / "tests" / "test_calc.py").write_text(TESTS, encoding="utf-8")
    return repo


def _ratchet(repo: Path, *args: str):
    return runner.invoke(app, ["proof", "ratchet", "-w", str(repo), "--json", *args])


def test_locked_and_not_locked_tests_are_listed(repo):
    result = _ratchet(repo)
    assert result.exit_code == 0, result.output
    doc = json.loads(result.stdout)
    assert doc["dry_run"] is False
    assert list(doc["locked"]) == ["test_add"]
    assert len(doc["req_ids"]) == 1
    assert doc["failed"] == ["test_broken"]
    assert doc["already_locked"] == []
    assert isinstance(doc["per_test_scope"], bool)
    assert doc["workspace_created"] is True
    assert "Running the test suite" in result.stderr


def test_a_rerun_reports_already_locked(repo):
    assert _ratchet(repo).exit_code == 0
    doc = json.loads(_ratchet(repo).stdout)
    assert doc["workspace_created"] is False
    assert doc["locked"] == {}
    assert doc["already_locked"] == ["test_add"]


def test_dry_run_writes_nothing(repo):
    result = _ratchet(repo, "--dry-run")
    assert result.exit_code == 0, result.output
    doc = json.loads(result.stdout)
    assert doc["dry_run"] is True
    assert doc["workspace_created"] is False
    assert list(doc["locked"]) == ["test_add"]
    assert not (repo / CODEFRAME_DIR).exists()


def test_nothing_to_lock_keeps_exit_2_and_reports_it(repo):
    (repo / "tests" / "test_calc.py").write_text(
        "def test_broken():\n    assert False\n", encoding="utf-8"
    )
    result = _ratchet(repo)
    assert result.exit_code == 2
    doc = json.loads(result.stdout)
    assert doc["locked"] == {}
    assert doc["failed"] == ["test_broken"]


def test_status_counts_ratchet_requirements_as_locked(repo):
    assert _ratchet(repo).exit_code == 0
    capture = runner.invoke(app, [
        "proof", "capture", "-w", str(repo), "--title", "t", "--description", "d",
        "--where", "calc.py", "--severity", "low", "--source", "qa",
    ])
    assert capture.exit_code == 0, capture.output
    result = runner.invoke(app, ["proof", "status", "-w", str(repo), "--json"])
    counts = json.loads(result.stdout)["counts"]
    assert counts["total"] == 2
    assert counts["locked"] == 1
