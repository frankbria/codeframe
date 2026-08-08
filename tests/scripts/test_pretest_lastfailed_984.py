"""The pre-commit fast-feedback hook must never expand to the full suite (#984).

``pytest --lf --lfnf none`` guards only the *empty* cache. With a non-empty
``lastfailed`` whose node IDs no longer resolve — a renamed, moved or deleted
test — pytest falls back to running everything. Reproduced before the fix:

    Case C (target exists):  1 test ran
    Case A (target renamed): all 3 ran, with --lfnf none in effect

That turns a no-op hook into a full-suite run carrying ``-x``. These tests pin
the selection the hook makes, not its output, because the defect is entirely
about *scope*.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "pretest_lastfailed.py"

SUITE = """\
def test_alpha_passes(): assert True
def test_beta_fails(): assert False
def test_gamma_passes(): assert True
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A tiny throwaway project with its own pytest cache."""
    (tmp_path / "test_gt.py").write_text(SUITE)
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    return tmp_path


def _write_lastfailed(project: Path, node_ids: list[str]) -> None:
    cache = project / ".pytest_cache" / "v" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "lastfailed").write_text(json.dumps({n: True for n in node_ids}))


def _selection(project: Path) -> list[str]:
    """What the hook would actually run, as node IDs."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--print-selection"],
        cwd=project,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return [line for line in result.stdout.splitlines() if line.strip()]


class TestStaleCacheSelectsNothing:
    """Case A — the bug."""

    def test_a_renamed_test_selects_nothing(self, project):
        _write_lastfailed(project, ["test_gt.py::test_beta_fails"])
        (project / "test_gt.py").write_text(
            SUITE.replace("test_beta_fails", "test_beta_renamed")
        )
        assert _selection(project) == [], (
            "a stale lastfailed entry expanded the hook's scope"
        )

    def test_a_deleted_file_selects_nothing(self, project):
        _write_lastfailed(project, ["test_gone.py::test_x"])
        assert _selection(project) == []

    def test_a_deleted_test_within_a_live_file_selects_nothing(self, project):
        _write_lastfailed(project, ["test_gt.py::test_beta_fails"])
        (project / "test_gt.py").write_text(
            "def test_alpha_passes(): assert True\n"
        )
        assert _selection(project) == []


class TestLiveCacheStillSelectsTheFailure:
    """Case C — the behaviour that must survive the fix."""

    def test_an_existing_failure_is_selected(self, project):
        _write_lastfailed(project, ["test_gt.py::test_beta_fails"])
        assert _selection(project) == ["test_gt.py::test_beta_fails"]

    def test_only_the_failure_is_selected_not_its_neighbours(self, project):
        _write_lastfailed(project, ["test_gt.py::test_beta_fails"])
        selection = _selection(project)
        assert "test_gt.py::test_alpha_passes" not in selection
        assert "test_gt.py::test_gamma_passes" not in selection

    def test_a_live_entry_survives_alongside_a_stale_one(self, project):
        """The mixed case: prune the dead, keep the living."""
        _write_lastfailed(
            project,
            ["test_gt.py::test_beta_fails", "test_gt.py::test_long_gone"],
        )
        assert _selection(project) == ["test_gt.py::test_beta_fails"]


class TestEmptyAndMissingCache:
    def test_no_cache_at_all_selects_nothing(self, project):
        assert _selection(project) == []

    def test_an_empty_cache_selects_nothing(self, project):
        _write_lastfailed(project, [])
        assert _selection(project) == []

    def test_malformed_cache_selects_nothing_rather_than_everything(self, project):
        """Fail safe: an unreadable cache must not mean 'run the suite'."""
        cache = project / ".pytest_cache" / "v" / "cache"
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "lastfailed").write_text("{not json")
        assert _selection(project) == []


class TestWholeFileKeys:
    """A collection error records the file itself, with no `::`."""

    def test_a_live_file_key_is_kept(self, project):
        _write_lastfailed(project, ["test_gt.py"])
        assert _selection(project) == ["test_gt.py"]

    def test_a_dead_file_key_is_dropped(self, project):
        _write_lastfailed(project, ["test_vanished.py"])
        assert _selection(project) == []


class TestItActuallyRuns:
    """The script is a hook entry point, not just a selector."""

    def _run(self, project: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=project,
            capture_output=True,
            text=True,
        )

    def test_a_stale_cache_exits_zero_without_running_tests(self, project):
        _write_lastfailed(project, ["test_gt.py::test_beta_fails"])
        (project / "test_gt.py").write_text(
            SUITE.replace("test_beta_fails", "test_beta_renamed")
        )
        result = self._run(project)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "3 passed" not in result.stdout, "ran the whole file anyway"

    def test_a_live_failure_still_fails_the_commit(self, project):
        _write_lastfailed(project, ["test_gt.py::test_beta_fails"])
        result = self._run(project)
        assert result.returncode != 0, "a real failure must still block the commit"

    def test_a_fixed_failure_passes(self, project):
        _write_lastfailed(project, ["test_gt.py::test_beta_fails"])
        (project / "test_gt.py").write_text(
            SUITE.replace("def test_beta_fails(): assert False",
                          "def test_beta_fails(): assert True")
        )
        assert self._run(project).returncode == 0
