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


#: This repo's own pytest.ini starts addopts with `-v`. Verbosity is a single
#: counter, so `-v` (ini) + `-q` (probe) nets to DEFAULT, and --collect-only
#: then prints an indented <Module>/<Function> tree with no "::" anywhere. A
#: bare ini hides that completely, which is why every fixture below is
#: parametrized over both.
INI_PLAIN = "[pytest]\n"
INI_VERBOSE = "[pytest]\naddopts =\n    -v\n    --strict-markers\n"


@pytest.fixture(params=[INI_PLAIN, INI_VERBOSE], ids=["plain-ini", "verbose-ini"])
def project(request, tmp_path: Path) -> Path:
    """A tiny throwaway project with its own pytest cache."""
    (tmp_path / "test_gt.py").write_text(SUITE)
    (tmp_path / "pytest.ini").write_text(request.param)
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


class TestAFileThatStoppedCollectingIsBreakage:
    """A syntax/import error is not staleness — it must block the commit.

    The two look alike from the outside: a cached node ID that no longer
    resolves. But a renamed test means "nothing to run", while a file that
    fails to import means "you just broke this", and pruning it would let the
    hook pass on exactly the change it exists to catch.
    """

    def test_a_broken_file_is_selected_not_pruned(self, project):
        _write_lastfailed(project, ["test_gt.py::test_beta_fails"])
        (project / "test_gt.py").write_text("def bad(: pass\n")
        assert _selection(project) == ["test_gt.py"]

    def test_a_broken_file_fails_the_hook(self, project):
        _write_lastfailed(project, ["test_gt.py::test_beta_fails"])
        (project / "test_gt.py").write_text("def bad(: pass\n")
        result = subprocess.run(
            [sys.executable, str(SCRIPT)], cwd=project, capture_output=True, text=True
        )
        assert result.returncode != 0, "a file that no longer imports let the commit through"

    def test_an_import_error_counts_too_not_just_syntax(self, project):
        _write_lastfailed(project, ["test_gt.py::test_beta_fails"])
        (project / "test_gt.py").write_text("import a_module_that_does_not_exist\n")
        assert _selection(project) == ["test_gt.py"]

    def test_a_healthy_file_is_unaffected_by_a_broken_neighbour(self, project):
        """Only the broken file is selected; the renamed one stays pruned."""
        (project / "test_other.py").write_text("def bad(: pass\n")
        _write_lastfailed(
            project,
            ["test_gt.py::test_beta_fails", "test_other.py::test_whatever"],
        )
        (project / "test_gt.py").write_text(
            SUITE.replace("test_beta_fails", "test_beta_renamed")
        )
        assert _selection(project) == ["test_other.py"]


class TestUnparseableCollectionFallsBackLoudly:
    """If the output shape is unreadable, do not conclude "all stale".

    `-o addopts=` handles the ini, but a conftest can raise verbosity in code,
    where no command-line flag can undo it. That prints the indented tree with
    no "::" anywhere — indistinguishable, to a naive parser, from "nothing
    resolved". Silently selecting nothing is the failure mode this whole issue
    is about, so the parser refuses to guess.
    """

    def _make_verbose_conftest(self, project: Path) -> None:
        (project / "conftest.py").write_text(
            "def pytest_configure(config):\n"
            "    config.option.verbose = max(config.option.verbose, 1)\n"
        )

    def test_it_falls_back_to_the_cached_files(self, project):
        self._make_verbose_conftest(project)
        _write_lastfailed(project, ["test_gt.py::test_beta_fails"])
        assert _selection(project) == ["test_gt.py"], (
            "unparseable collection silently selected nothing"
        )

    def test_it_says_so_on_stderr(self, project):
        self._make_verbose_conftest(project)
        _write_lastfailed(project, ["test_gt.py::test_beta_fails"])
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--print-selection"],
            cwd=project, capture_output=True, text=True,
        )
        assert "could not parse" in result.stderr.lower(), result.stderr

    def test_the_fallback_still_blocks_a_real_failure(self, project):
        self._make_verbose_conftest(project)
        _write_lastfailed(project, ["test_gt.py::test_beta_fails"])
        result = subprocess.run(
            [sys.executable, str(SCRIPT)], cwd=project, capture_output=True, text=True
        )
        assert result.returncode != 0

    def test_it_fires_even_when_one_file_also_errored(self, project):
        """The mixed case: a broken file must not suppress the guard.

        `errored` is populated by an "ERROR collecting" regex that does not
        care about verbosity, so it stays non-empty while `resolved` is empty.
        Gating the guard on `not errored` would let the healthy file's
        still-failing test be pruned as stale.
        """
        self._make_verbose_conftest(project)
        (project / "test_broken.py").write_text("def bad(: pass\n")
        _write_lastfailed(
            project,
            ["test_gt.py::test_beta_fails", "test_broken.py::test_x"],
        )
        selection = _selection(project)
        assert "test_gt.py" in selection, (
            "the healthy file's live failure was pruned as stale"
        )

    def test_the_fallback_is_still_bounded_to_cached_files(self, project):
        """Falling back must not become the full-suite run we are preventing."""
        self._make_verbose_conftest(project)
        (project / "test_untouched.py").write_text("def test_nope(): assert False\n")
        _write_lastfailed(project, ["test_gt.py::test_beta_fails"])
        assert "test_untouched.py" not in _selection(project)


class TestWholeFileKeys:
    """A collection error records the file itself, with no `::`."""

    def test_a_live_file_key_is_kept(self, project):
        _write_lastfailed(project, ["test_gt.py"])
        assert _selection(project) == ["test_gt.py"]

    def test_a_dead_file_key_is_dropped(self, project):
        _write_lastfailed(project, ["test_vanished.py"])
        assert _selection(project) == []


class TestAMixedSelectionReportsBoth:
    """A broken neighbour must not swallow the failure you came to see.

    `pytest -x broken.py live.py::test_x` aborts the whole session on the
    collection error before running anything, so the live failure never
    executes or reports. The commit is still blocked — the safety invariant
    holds — but the developer sees "1 error during collection" instead of
    their assertion, which is the wrong thing to debug.
    """

    def test_the_live_failure_is_actually_reported(self, project):
        (project / "test_broken.py").write_text("def bad(: pass\n")
        _write_lastfailed(
            project,
            ["test_gt.py::test_beta_fails", "test_broken.py::test_x"],
        )
        result = subprocess.run(
            [sys.executable, str(SCRIPT)], cwd=project, capture_output=True, text=True
        )
        assert result.returncode != 0
        assert "test_beta_fails" in result.stdout, (
            "the live failure was swallowed by the broken neighbour's "
            f"collection abort:\n{result.stdout[-800:]}"
        )

    def test_a_broken_file_alone_still_fails(self, project):
        (project / "test_broken.py").write_text("def bad(: pass\n")
        _write_lastfailed(project, ["test_broken.py::test_x"])
        result = subprocess.run(
            [sys.executable, str(SCRIPT)], cwd=project, capture_output=True, text=True
        )
        assert result.returncode != 0

    def test_a_broken_file_is_reported_when_the_live_ones_pass(self, project):
        """Fail-fast must not hide the collection error behind a green run."""
        (project / "test_broken.py").write_text("def bad(: pass\n")
        (project / "test_gt.py").write_text(
            SUITE.replace("def test_beta_fails(): assert False",
                          "def test_beta_fails(): assert True")
        )
        _write_lastfailed(
            project,
            ["test_gt.py::test_beta_fails", "test_broken.py::test_x"],
        )
        result = subprocess.run(
            [sys.executable, str(SCRIPT)], cwd=project, capture_output=True, text=True
        )
        assert result.returncode != 0, "the collection error was not reported"


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
