"""`uv run pytest` must not spend money or touch an external project (#946).

Three defects, all reachable by running the repo's own documented quality
command on a developer machine:

1. `pytest.ini` had `testpaths = tests` and no marker deselection, so plain
   `uv run pytest` collected and RAN `test_react_engine_validation.py` — a full
   Golden Path with `timeout_per_task=600` making real Anthropic calls, whose
   `clean_cf_test` fixture `rmtree`s `.codeframe/` inside the EXTERNAL
   `~/projects/cf-test`.
2. `tests/e2e/cli/conftest.py` called `_ensure_api_key()` at import time,
   copying the production key out of the repo's `.env` into `os.environ` during
   COLLECTION of any `pytest tests/` run. That also flipped `requires_api_key`
   gates from skip to run.
3. Every validator passes `timeout=` but caught only `OSError`.
   `subprocess.TimeoutExpired` is a `SubprocessError`, so a hanging command
   escaped the validator and aborted the module fixture instead of being
   recorded as a failed check.

These live at the tests root, not under `tests/e2e/`, because CI's gate runs
`--ignore=tests/e2e` — a regression test inside that tree would never run.
"""

import configparser
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

REPO_ROOT = Path(__file__).resolve().parent.parent
E2E_CLI = REPO_ROOT / "tests" / "e2e" / "cli"


def _addopts() -> list[str]:
    parser = configparser.ConfigParser()
    parser.read(REPO_ROOT / "pytest.ini")
    return shlex.split(parser["pytest"]["addopts"], comments=True)


class TestExpensiveMarkersAreDeselectedByDefault:
    def test_addopts_carries_a_marker_expression(self):
        assert "-m" in _addopts(), (
            "nothing deselects the paid markers, so plain `pytest` runs them"
        )

    @pytest.mark.parametrize("marker", ["e2e_llm", "lifecycle"])
    def test_the_expression_excludes_the_marker(self, marker: str):
        opts = _addopts()
        expr = opts[opts.index("-m") + 1]

        assert f"not {marker}" in expr, f"{marker} is not deselected: {expr!r}"

    def test_a_bare_run_collects_zero_expensive_tests(self):
        """AC2, measured — the ini could say anything; this asks pytest."""
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/e2e"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=180,
        )

        # "N/M tests collected (K deselected)" — the paid ones must be in K.
        assert "e2e_llm" not in proc.stdout, proc.stdout[-2000:]
        assert "test_react_engine_validation" not in proc.stdout, (
            "the paid Golden Path test is still collected by a default run"
        )

    def test_an_explicit_opt_in_still_selects_them(self):
        """The deselection must be a default, not a wall."""
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                "--collect-only", "-q", "-m", "e2e_llm", "tests/e2e",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=180,
        )

        assert "test_react_engine_validation" in proc.stdout, (
            "`-m e2e_llm` no longer reaches the tests it names"
        )


class TestCollectionDoesNotLeakTheApiKey:
    def test_the_conftest_does_not_load_the_key_at_import_time(self):
        source = E2E_CLI / "conftest.py"
        code = "\n".join(
            line.split("#")[0] for line in source.read_text().splitlines()
        )

        assert "_ensure_api_key()" not in code, (
            "the key is still copied into os.environ during collection"
        )

    def test_importing_the_conftest_leaves_the_environment_alone(self):
        """AC3, measured in a child process so this test cannot poison itself.

        Importing the conftest is exactly what collection does. Run with the
        variable explicitly unset; if the import puts it back, the child says
        LEAKED. This fails against the previous conftest.
        """
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        probe = (
            "import os, sys, importlib;"
            "importlib.import_module('tests.e2e.cli.conftest');"
            "sys.stdout.write("
            "'LEAKED' if os.environ.get('ANTHROPIC_API_KEY') else 'CLEAN')"
        )
        proc = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )

        assert proc.stdout.endswith("CLEAN"), (
            f"importing the conftest wrote ANTHROPIC_API_KEY into os.environ: "
            f"{proc.stdout!r} {proc.stderr[-500:]!r}"
        )

    def test_the_key_fixture_puts_it_back_the_way_it_found_it(self):
        """It is a generator fixture with a finally, not a plain return."""
        source = (E2E_CLI / "conftest.py").read_text()
        body = source.split("def anthropic_api_key(")[1].split("\n@pytest")[0]

        assert "yield" in body, "the fixture cannot clean up after a bare return"
        assert 'os.environ.pop("ANTHROPIC_API_KEY", None)' in body


class TestValidatorsSurviveAHangingCommand:
    """AC4. `subprocess.TimeoutExpired` subclasses `SubprocessError`, so the
    existing `except OSError` never caught it."""

    @pytest.fixture
    def hang(self, monkeypatch):
        """Make every subprocess.run in validators time out."""
        from tests.e2e.cli import validators

        def _timeout(argv, **kwargs):
            raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout", 1))

        monkeypatch.setattr(validators.subprocess, "run", _timeout)
        return validators

    @pytest.mark.parametrize(
        "name",
        [
            "validate_ruff_lint",
            "validate_tests_pass",
            "validate_cli_works",
            "validate_no_import_errors",
        ],
    )
    def test_a_timeout_is_a_failed_check_not_an_exception(self, hang, name, tmp_path):
        passed, detail = getattr(hang, name)(tmp_path)

        assert passed is False
        assert "timed out" in detail, f"{name} reported {detail!r}"

    def test_the_report_still_aggregates_when_everything_hangs(self, hang, tmp_path):
        """The point of the tuple contract: one hung tool must not cost the
        results of the seven other checks."""
        run = type("R", (), {"task_results": []})()

        results = hang.run_all_validators(tmp_path, run, original_pyproject_hash="x")

        assert len(results) == 8
        assert all(isinstance(v, tuple) for v in results.values())

    def test_the_non_subprocess_validators_are_unaffected(self, hang, tmp_path):
        """They never call subprocess, so a hang must not change their verdict."""
        run = type("R", (), {"task_results": []})()

        assert hang.validate_iteration_counts(run)[0] is True

    def test_a_genuinely_hanging_command(self, monkeypatch, tmp_path):
        """AC4 verbatim: a real process that really outlives its timeout, not a
        raised exception. The monkeypatched cases above prove the handler; this
        proves the handler is reached by the thing it was written for."""
        from tests.e2e.cli import validators

        real_run = subprocess.run
        monkeypatch.setattr(
            validators.subprocess,
            "run",
            lambda argv, **kw: real_run(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                **{**kw, "timeout": 1},
            ),
        )

        passed, detail = validators.validate_ruff_lint(tmp_path)

        assert passed is False
        assert "timed out" in detail


class TestTheCiSelectorDoesNotReSelectThem:
    """A `-m` on the command line REPLACES the one in addopts rather than
    combining with it, so every CI invocation that passes its own -m has to
    exclude the paid markers itself."""

    def test_the_e2e_job_excludes_e2e_llm(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "test.yml").read_text()

        assert '-m "e2e and not e2e_llm"' in workflow, (
            "the E2E job's -m re-selects the paid real-LLM tests"
        )

    def test_the_backend_job_ignores_the_e2e_tree_entirely(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "test.yml").read_text()

        assert "--ignore=tests/e2e" in workflow
