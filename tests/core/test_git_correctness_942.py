"""core/git commit and diff correctness (#942).

Five defects, all of which put wrong data in the user's repository or their
patch file:

1. `create_commit` staged the requested files then called `repo.index.commit()`,
   which commits the **entire index** — anything an agent run left staged was
   swept into the user's commit, while `files_changed` reported only what they
   asked for.
2. It skipped paths that do not exist, so a deletion `get_status` offered as
   committable was silently dropped from a 201, and a deletions-only request
   failed with "None of the specified files exist".
3. `get_diff_stats` labelled every rename "modified" and re-scanned the whole
   diff text once per changed file.
4. `export_patch(staged_only=True)` fell back to plain `git diff`, exporting
   **unstaged** work under a filename claiming "staged".
5. Nothing ever wrote a `.codeframe/` ignore rule although the sandbox code
   assumed it, so `cf commit --all` could stage `state.db` into user history.
"""

import subprocess
from pathlib import Path

import pytest

from codeframe.core import artifacts
from codeframe.core import git as core_git
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


def _run(*args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)


@pytest.fixture
def repo(tmp_path):
    """A real git repo with one committed file."""
    _run("git", "init", "-q", cwd=tmp_path)
    _run("git", "config", "user.email", "t@t.test", cwd=tmp_path)
    _run("git", "config", "user.name", "T", cwd=tmp_path)
    (tmp_path / "kept.txt").write_text("original\n")
    (tmp_path / "doomed.txt").write_text("delete me\n")
    _run("git", "add", "-A", cwd=tmp_path)
    _run("git", "commit", "-qm", "init", cwd=tmp_path)
    return tmp_path


@pytest.fixture
def workspace(repo):
    return create_or_load_workspace(repo)


def _committed_files(repo_path: Path) -> set[str]:
    out = _run("git", "show", "--name-only", "--pretty=format:", "HEAD", cwd=repo_path)
    return {line.strip() for line in out.stdout.splitlines() if line.strip()}


class TestCommitOnlyTheRequestedPaths:
    def test_a_pre_staged_unrelated_file_is_not_swept_in(self, workspace, repo):
        """The headline defect: an agent run's leftovers landing in a user commit."""
        (repo / "unrelated.txt").write_text("agent leftovers\n")
        _run("git", "add", "unrelated.txt", cwd=repo)

        (repo / "wanted.txt").write_text("what the user asked for\n")
        result = core_git.create_commit(workspace, ["wanted.txt"], "add wanted")

        committed = _committed_files(repo)
        assert "wanted.txt" in committed
        assert "unrelated.txt" not in committed, (
            "a pre-staged unrelated file was swept into the commit"
        )
        assert result.files_changed == 1

    def test_the_unrelated_file_remains_staged_afterwards(self, workspace, repo):
        """Excluding it must not silently discard the user's other work."""
        (repo / "unrelated.txt").write_text("agent leftovers\n")
        _run("git", "add", "unrelated.txt", cwd=repo)
        (repo / "wanted.txt").write_text("x\n")

        core_git.create_commit(workspace, ["wanted.txt"], "add wanted")

        staged = _run("git", "diff", "--cached", "--name-only", cwd=repo).stdout
        assert "unrelated.txt" in staged


class TestDeletionsAreCommittable:
    def test_a_deletions_only_request_succeeds(self, workspace, repo):
        (repo / "doomed.txt").unlink()

        result = core_git.create_commit(workspace, ["doomed.txt"], "remove doomed")

        assert result.files_changed == 1
        assert "doomed.txt" in _committed_files(repo)
        tracked = _run("git", "ls-files", cwd=repo).stdout
        assert "doomed.txt" not in tracked, "the file is still tracked"

    def test_a_mixed_add_and_delete_request_works(self, workspace, repo):
        (repo / "doomed.txt").unlink()
        (repo / "fresh.txt").write_text("new\n")

        result = core_git.create_commit(
            workspace, ["doomed.txt", "fresh.txt"], "swap"
        )

        assert result.files_changed == 2
        assert {"doomed.txt", "fresh.txt"} <= _committed_files(repo)

    def test_skipped_paths_are_reported_not_silently_dropped(self, workspace, repo):
        (repo / "real.txt").write_text("x\n")

        result = core_git.create_commit(
            workspace, ["real.txt", "never-existed.txt"], "partial"
        )

        assert result.files_changed == 1
        assert "never-existed.txt" in result.skipped, (
            "a dropped path was invisible in the response"
        )

    def test_all_paths_missing_still_raises(self, workspace):
        with pytest.raises(ValueError, match="None of the specified files exist"):
            core_git.create_commit(workspace, ["nope.txt"], "msg")


class TestDiffStatsLabelsRenames:
    def test_a_rename_is_reported_as_renamed_with_the_new_path(self, workspace, repo):
        _run("git", "mv", "kept.txt", "renamed.txt", cwd=repo)

        stats = core_git.get_diff_stats(workspace, staged=True)

        by_type = {f.change_type for f in stats.changed_files}
        assert "renamed" in by_type, (
            f"rename reported as {by_type} — every rename used to be 'modified'"
        )
        paths = {f.path for f in stats.changed_files}
        assert any("renamed.txt" in p for p in paths), "the NEW path must be reported"

    def test_added_and_deleted_are_still_correct(self, workspace, repo):
        (repo / "added.txt").write_text("new\n")
        (repo / "doomed.txt").unlink()
        _run("git", "add", "-A", cwd=repo)

        stats = core_git.get_diff_stats(workspace, staged=True)
        types = {f.path: f.change_type for f in stats.changed_files}

        assert types.get("added.txt") == "added"
        assert types.get("doomed.txt") == "deleted"

    def test_the_diff_is_indexed_once(self):
        """AC3's other half — the old code re-scanned the whole diff per file."""
        import inspect

        source = inspect.getsource(core_git.get_diff_stats)

        assert "_index_diff_sections(" in source
        assert "re.search(" not in source, "still scanning the diff per file"


class TestStagedOnlyPatchDoesNotExportUnstagedWork:
    def test_empty_index_reports_no_staged_changes(self, workspace, repo):
        # Unstaged work exists; nothing is staged.
        (repo / "kept.txt").write_text("edited but not staged\n")

        with pytest.raises(ValueError, match="[Nn]o staged changes"):
            artifacts.export_patch(workspace, staged_only=True)

    def test_it_does_not_write_a_patch_of_the_unstaged_work(self, workspace, repo):
        (repo / "kept.txt").write_text("edited but not staged\n")

        with pytest.raises(ValueError):
            artifacts.export_patch(workspace, staged_only=True)

        patches = list((repo / ".codeframe").rglob("*.patch"))
        assert not patches, "an unstaged diff was written as a 'staged' patch"

    def test_real_staged_changes_still_export(self, workspace, repo):
        (repo / "kept.txt").write_text("staged edit\n")
        _run("git", "add", "kept.txt", cwd=repo)

        info = artifacts.export_patch(workspace, staged_only=True)

        assert Path(info.path).exists()


class TestStateDirIsIgnored:
    def test_git_add_all_stages_nothing_under_codeframe(self, tmp_path):
        _run("git", "init", "-q", cwd=tmp_path)
        create_or_load_workspace(tmp_path)

        _run("git", "add", "-A", cwd=tmp_path)
        staged = _run("git", "diff", "--cached", "--name-only", cwd=tmp_path).stdout

        offenders = [ln for ln in staged.splitlines() if ".codeframe" in ln]
        assert not offenders, f"state files would enter user history: {offenders}"

    def test_the_marker_lives_inside_the_state_dir(self, tmp_path):
        """Not the repo's root .gitignore — that file belongs to the user."""
        _run("git", "init", "-q", cwd=tmp_path)
        create_or_load_workspace(tmp_path)

        assert (tmp_path / ".codeframe" / ".gitignore").exists()
        assert not (tmp_path / ".gitignore").exists(), (
            "the user's root .gitignore was created or edited"
        )

    def test_an_existing_marker_is_not_overwritten(self, tmp_path):
        _run("git", "init", "-q", cwd=tmp_path)
        state = tmp_path / ".codeframe"
        state.mkdir()
        (state / ".gitignore").write_text("# user's own\n*\n")

        create_or_load_workspace(tmp_path)

        assert "user's own" in (state / ".gitignore").read_text()
