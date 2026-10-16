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


def _run_lifecycle(*args, drop_api_key: bool = False) -> subprocess.CompletedProcess:
    """--dry-run so nothing is executed and no key is spent.

    ``drop_api_key`` omits ANTHROPIC_API_KEY entirely, which is how the `api`
    mode is meant to run — on the mock provider, for free, on every PR.
    """
    env = {"PATH": "/usr/bin:/bin"}
    if not drop_api_key:
        # The script exits early without a key, which would mask the mode check.
        env["ANTHROPIC_API_KEY"] = "not-a-real-key"
    return subprocess.run(
        [str(LIFECYCLE), *args, "--dry-run"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def _e2e_backend_job() -> dict:
    workflow = yaml.safe_load(WORKFLOW.read_text())
    return workflow["jobs"]["e2e-backend-tests"]


class TestEveryAdvertisedModeIsReal:
    """AC1. Every mode the help text offers must resolve to a suite, and any
    other mode must be refused rather than report success for nothing. `api`
    and `web` were real until the server and web UI went (#1477); they are
    refused now, exactly like a typo.
    """

    @pytest.mark.parametrize("mode", ["cli"])
    def test_the_mode_resolves_to_a_real_suite(self, mode: str):
        proc = _run_lifecycle("--mode", mode)

        assert proc.returncode == 0, proc.stderr
        assert "not implemented" not in proc.stderr.lower(), proc.stderr

    @pytest.mark.parametrize("mode", ["banana", "api", "web", "all"])
    def test_any_other_mode_is_rejected(self, mode: str):
        assert _run_lifecycle("--mode", mode).returncode != 0

    def test_cli_mode_runs_the_paid_suite(self):
        proc = _run_lifecycle("--mode", "cli")

        assert "test_cli_lifecycle.py" in proc.stdout
        assert "-m lifecycle" in proc.stdout


    def test_the_help_text_offers_every_working_mode(self):
        proc = subprocess.run(
            [str(LIFECYCLE), "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert "--mode cli" in proc.stdout
        assert "api" not in proc.stdout.split("--mode", 1)[1].split("\n", 1)[0], (
            "the help text must not offer a mode that was removed"
        )
        assert "not implemented" not in proc.stdout.lower()


class TestNoAdvertisedModeCollectsOnlySkips:
    """AC1's second half, measured rather than assumed."""

    def test_the_python_web_stub_is_still_gone(self):
        """#948 deleted this stub. If the filename reappears, something
        recreated a suite for a surface that no longer exists (#1477)."""
        assert not (REPO_ROOT / "tests" / "lifecycle" / "test_web_lifecycle.py").exists()


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
