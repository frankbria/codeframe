"""Three advertised quality gates were green theatre (#948).

1. CLAUDE.md names `scripts/lifecycle --mode cli|api|web|all` as the pre-PR
   gate. `test_api_lifecycle.py` and `test_web_lifecycle.py` were class-level
   `@pytest.mark.skip` stubs whose methods `raise NotImplementedError`, so
   three of the four modes collected only skips and exited **0**. Two of them
   reported success for work that did not exist.
2. The `e2e-backend-tests` job booted uvicorn and polled `/health` for up to
   120 seconds — while not one test under `tests/e2e` makes an HTTP request.
   And a run in which everything skipped exited 0 and read as a pass.
3. `.coveragerc` had `fail_under` commented out, with a rationale `pytest.ini`
   itself declares obsolete, while the README shipped an 88% badge and a
   ">85% coverage" contribution rule that nothing enforced.

These are meta-tests: they assert on the repository's own gate configuration,
which is where the defect lives. They run in the default CI gate.
"""

import configparser
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.v2

REPO_ROOT = Path(__file__).resolve().parent.parent
LIFECYCLE = REPO_ROOT / "scripts" / "lifecycle"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "test.yml"


def _run_lifecycle(*args) -> subprocess.CompletedProcess:
    """--dry-run so nothing is executed and no key is spent."""
    return subprocess.run(
        [str(LIFECYCLE), *args, "--dry-run"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        # The script exits early without a key, which would mask the mode check.
        env={"PATH": "/usr/bin:/bin", "ANTHROPIC_API_KEY": "not-a-real-key"},
        timeout=60,
    )


def _e2e_backend_job() -> dict:
    workflow = yaml.safe_load(WORKFLOW.read_text())
    return workflow["jobs"]["e2e-backend-tests"]


class TestUnimplementedLifecycleModesFailLoudly:
    """AC1. The modes must not report success for a suite that does not exist."""

    @pytest.mark.parametrize("mode", ["api", "web"])
    def test_the_mode_exits_non_zero(self, mode: str):
        proc = _run_lifecycle("--mode", mode)

        assert proc.returncode != 0, (
            f"--mode {mode} still exits 0 — a caller reads that as a pass"
        )

    @pytest.mark.parametrize("mode", ["api", "web"])
    def test_it_says_why_and_points_somewhere(self, mode: str):
        proc = _run_lifecycle("--mode", mode)

        assert "not implemented" in proc.stderr.lower(), proc.stderr
        assert "#1068" in proc.stderr, "no pointer to the tracking issue"

    @pytest.mark.parametrize("mode", ["api", "web"])
    def test_its_exit_code_differs_from_a_typo(self, mode: str):
        """`--mode api` and `--mode banana` are different failures: one is
        "not built yet", the other is "you mistyped". Same code would conflate
        them for any script wrapping this one."""
        unimplemented = _run_lifecycle("--mode", mode).returncode
        typo = _run_lifecycle("--mode", "banana").returncode

        assert unimplemented != typo

    def test_the_implemented_mode_still_works(self):
        proc = _run_lifecycle("--mode", "cli")

        assert proc.returncode == 0, proc.stderr
        assert "test_cli_lifecycle.py" in proc.stdout

    def test_all_still_works(self):
        proc = _run_lifecycle("--mode", "all")

        assert proc.returncode == 0, proc.stderr

    def test_the_help_text_no_longer_advertises_them(self):
        proc = subprocess.run(
            [str(LIFECYCLE), "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert "cli|api|web|all" not in proc.stdout, (
            "--help still offers the two modes that cannot run"
        )


class TestNoAdvertisedModeCollectsOnlySkips:
    """AC1's second half, measured rather than assumed."""

    def test_the_stub_files_are_gone(self):
        for name in ("test_api_lifecycle.py", "test_web_lifecycle.py"):
            assert not (REPO_ROOT / "tests" / "lifecycle" / name).exists(), (
                f"{name} still exists — pytest will collect its skips"
            )

    def test_the_remaining_lifecycle_suite_has_real_tests(self):
        """Not `raise NotImplementedError` in a skipped class."""
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                "--collect-only", "-q", "-m", "lifecycle", "tests/lifecycle",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=180,
        )

        assert "test_cli_lifecycle" in proc.stdout, proc.stdout[-1500:]

    def test_no_lifecycle_test_is_a_bare_not_implemented(self):
        for path in (REPO_ROOT / "tests" / "lifecycle").glob("test_*.py"):
            source = path.read_text()
            assert "raise NotImplementedError" not in source, (
                f"{path.name} still contains a stub body"
            )


class TestE2eBackendJobIsHonest:
    """AC2."""

    def test_it_no_longer_boots_a_server_nothing_talks_to(self):
        steps = yaml.safe_dump(_e2e_backend_job()["steps"])

        assert "uvicorn" not in steps, (
            "the job still starts a server; no test under tests/e2e makes an "
            "HTTP request"
        )
        assert "localhost:8080/health" not in steps

    def test_no_test_under_e2e_makes_an_http_request(self):
        """The premise of the step above. If this ever fails, the server boot
        should come BACK, not stay deleted."""
        offenders = []
        for path in (REPO_ROOT / "tests" / "e2e").rglob("*.py"):
            if "node_modules" in path.parts:
                continue
            source = path.read_text()
            code = "\n".join(ln.split("#")[0] for ln in source.splitlines())
            if any(
                token in code
                for token in ("requests.get", "requests.post", "httpx.", "aiohttp.")
            ):
                offenders.append(path.name)

        assert not offenders, f"these now need a live server: {offenders}"

    def test_the_teardown_and_log_artifact_went_with_it(self):
        steps = yaml.safe_dump(_e2e_backend_job()["steps"])

        assert "BACKEND_PID" not in steps
        assert "/tmp/server.log" not in steps

    def test_a_skipped_everything_run_fails_the_job(self):
        """pytest exits 5 on "collected nothing" but has no equivalent for
        "collected only skips", so the job asserts on the summary line."""
        steps = yaml.safe_dump(_e2e_backend_job()["steps"])

        assert "passed" in steps and "exit 1" in steps
        assert any(
            s.get("name") == "Fail if nothing actually ran"
            for s in _e2e_backend_job()["steps"]
        )

    def test_the_guard_is_not_defeated_by_a_pipe_swallowing_the_exit_code(self):
        """The run pipes pytest into tee. Without pipefail, tee's 0 wins and a
        real test failure passes the step."""
        run_step = next(
            s
            for s in _e2e_backend_job()["steps"]
            if s.get("name") == "Run E2E backend tests"
        )

        assert "| tee" in run_step["run"]
        assert "set -o pipefail" in run_step["run"], (
            "piping into tee discards pytest's exit code"
        )

    def test_the_guards_grep_matches_a_real_pytest_summary(self):
        """The regex is the whole gate; a mismatch makes it always-fail or, if
        someone loosens it, always-pass."""
        import re

        pattern = re.compile(r"[0-9]+ passed")

        assert pattern.search("== 23 passed, 20 deselected in 0.36s ==")
        assert pattern.search("== 1 passed, 4 skipped in 1.00s ==")
        assert not pattern.search("== 23 skipped, 20 deselected in 0.36s ==")
        assert not pattern.search("== no tests ran in 0.30s ==")


class TestCoverageThresholdIsEnforced:
    """AC3. A number in a README that nothing checks is decoration."""

    def _coveragerc(self) -> configparser.ConfigParser:
        parser = configparser.ConfigParser()
        parser.read(REPO_ROOT / ".coveragerc")
        return parser

    def test_fail_under_is_set(self):
        parser = self._coveragerc()

        assert parser.has_option("report", "fail_under"), (
            "fail_under is still commented out"
        )

    def test_the_backend_job_actually_runs_with_it(self):
        """`fail_under` only bites when a coverage REPORT runs. `pytest --cov`
        applies it, so the gate has to keep asking for coverage."""
        workflow = yaml.safe_load(WORKFLOW.read_text())
        steps = yaml.safe_dump(workflow["jobs"]["backend-tests"]["steps"])

        assert "--cov=codeframe" in steps

    def test_the_readme_claim_matches_the_enforced_number(self):
        """The point of the AC: the badge, the prose and the gate agree."""
        threshold = self._coveragerc().getint("report", "fail_under")
        readme = (REPO_ROOT / "README.md").read_text()

        assert f"coverage-{threshold}%25" in readme, (
            f"the badge does not show the enforced {threshold}%"
        )

    def test_the_contribution_rule_is_not_above_what_is_enforced(self):
        """README told contributors "85%+"; nothing checked it. Whatever it
        claims now must be a number the gate will actually hold them to."""
        import re

        threshold = self._coveragerc().getint("report", "fail_under")
        readme = (REPO_ROOT / "README.md").read_text()

        claims = [int(m) for m in re.findall(r"(\d{2})%\+? test coverage", readme)]
        assert claims, "the contribution rule vanished rather than being fixed"
        for claim in claims:
            assert claim <= threshold, (
                f"README asks contributors for {claim}% but CI enforces {threshold}%"
            )

    def test_no_commented_out_fail_under_remains(self):
        """The old rationale ("CI runs only -m v2 tests" — obsolete since #669,
        as pytest.ini itself says) sat above a commented-out `# fail_under`,
        which reads as a threshold to anyone skimming. Assert on the disabled
        DIRECTIVE, not on prose: the live comment explains why 80 was chosen
        and quotes the old claim, so a prose match would flag itself."""
        for line in (REPO_ROOT / ".coveragerc").read_text().splitlines():
            stripped = line.strip()
            assert not (stripped.startswith("#") and "fail_under" in stripped), (
                f"a commented-out threshold survives: {stripped!r}"
            )
