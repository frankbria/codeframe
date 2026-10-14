"""#1464 — `cf proof capture` creates the workspace on first use.

Capture was the one PROOF9 entry point a stranger could not reach: it raised
"No workspace found" until `cf init` had been run, which meant adopting the
pipeline before recording a single defect. Capture now creates `.codeframe/`
itself. Every other proof command still refuses a workspace that does not
exist, and capture never creates one in the wrong place.
"""

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core.proof import ledger
from codeframe.core.workspace import create_or_load_workspace, get_workspace

pytestmark = pytest.mark.v2

runner = CliRunner()

NOTICE = "Created .codeframe/ in this repository."

_ARGS = [
    "--title", "add() is wrong for negatives",
    "--description", "add(-1, -1) returned 0, expected -2",
    "--where", "calc.py",
    "--severity", "high",
    "--source", "qa",
]


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return repo


def _capture(path: Path, args: list[str] = _ARGS):
    return runner.invoke(app, ["proof", "capture", "-w", str(path)] + args)


class TestCaptureCreatesTheWorkspace:
    def test_capture_in_an_uninitialised_git_repo_creates_the_ledger(self, git_repo):
        result = _capture(git_repo)

        assert result.exit_code == 0, result.output
        reqs = ledger.list_requirements(get_workspace(git_repo))
        assert [r.title for r in reqs] == ["add() is wrong for negatives"]

    def test_the_notice_appears_only_when_the_directory_was_created(self, git_repo):
        first = _capture(git_repo)
        second = _capture(git_repo)

        assert NOTICE in first.output
        assert second.exit_code == 0, second.output
        assert NOTICE not in second.output

    def test_no_notice_for_a_workspace_that_already_existed(self, git_repo):
        create_or_load_workspace(git_repo)

        assert NOTICE not in _capture(git_repo).output


class TestCaptureCreatesItInTheRightPlace:
    def test_from_a_subdirectory_it_is_created_at_the_git_top_level(self, git_repo):
        sub = git_repo / "src" / "pkg"
        sub.mkdir(parents=True)

        result = _capture(sub)

        assert result.exit_code == 0, result.output
        assert (git_repo / ".codeframe" / "state.db").is_file()
        assert not (sub / ".codeframe").exists()
        assert not (git_repo / "src" / ".codeframe").exists()

    def test_from_a_subdirectory_of_a_workspace_it_uses_that_workspace(self, git_repo):
        workspace = create_or_load_workspace(git_repo)
        sub = git_repo / "src"
        sub.mkdir()

        result = _capture(sub)

        assert result.exit_code == 0, result.output
        assert not (sub / ".codeframe").exists()
        assert len(ledger.list_requirements(workspace)) == 1

    def test_a_repo_nested_in_another_workspace_gets_its_own(self, tmp_path, git_repo):
        """The parent workspace is outside this repository; its ledger is not ours."""
        parent = create_or_load_workspace(tmp_path)

        result = _capture(git_repo)

        assert result.exit_code == 0, result.output
        assert (git_repo / ".codeframe" / "state.db").is_file()
        assert ledger.list_requirements(parent) == []

    def test_outside_a_git_repo_it_refuses_and_creates_nothing(self, tmp_path):
        plain = tmp_path / "plain"
        plain.mkdir()

        result = _capture(plain)

        assert result.exit_code == 1
        assert "git repository" in result.output
        assert not (plain / ".codeframe").exists()

    def test_it_refuses_the_home_directory(self, git_repo, monkeypatch):
        """~/.codeframe is the machine-wide store; a state.db there would make
        every path under $HOME resolve to one workspace."""
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        result = _capture(git_repo)

        assert result.exit_code == 1
        assert not (git_repo / ".codeframe" / "state.db").exists()

    def test_a_rejected_capture_leaves_nothing_behind(self, git_repo):
        args = [a if a != "high" else "catastrophic" for a in _ARGS]

        result = _capture(git_repo, args)

        assert result.exit_code == 1
        assert not (git_repo / ".codeframe").exists()


class TestOnlyCaptureCreates:
    @pytest.mark.parametrize(
        "command",
        [
            ["run"],
            ["list"],
            ["status"],
            ["show", "REQ-0001"],
            ["waive", "REQ-0001", "--reason", "r"],
        ],
    )
    def test_other_proof_commands_still_refuse_a_missing_workspace(self, git_repo, command):
        result = runner.invoke(app, ["proof", *command, "-w", str(git_repo)])

        assert result.exit_code == 1, result.output
        assert not (git_repo / ".codeframe").exists()
