"""The public repo shipped one operator's laptop and three scripts that lie (#969).

`scripts/deploy.sh` printed "Deployment simulation successful" and exited 0 without
deploying — wired into a pipeline it is a green step and no deployment.
`seed-staging.sh` faked success against the removed v1 `/api/projects`.
`install-systemd-service.sh` installed a unit file that had already been deleted.
The health-check unit named the maintainer's account in `User=` and repeated their
home directory in four paths, and 38 dated AI session-scratch files sat in
`claudedocs/` in a repo prospective customers clone.

These are the checks that keep it purged. They are deliberately about *classes* of
defect, not a list of filenames: a script that claims success without doing work, a
tracked path that only exists on one machine, an installer pointing at a file that
is not there.
"""

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Frozen v1 history (see CLAUDE.md "Legacy (v1 reference only)"). These are a
#: record of what was, not instructions anyone runs, so they are not rewritten.
FROZEN = ("legacydocs/", "specs/", "sprints/")

#: `/home/<somebody>` — but a documentation placeholder is fine. `/home/user` is
#: what QUICKSTART shows; `$USER` and `<user>` are what a parameterized script uses.
PERSONAL_HOME = re.compile(r"/home/(?!user\b|\$\{?USER|<user>|%u\b)[A-Za-z_][\w.-]*")

#: systemd `User=` naming a literal account rather than a substituted placeholder.
LITERAL_SYSTEMD_USER = re.compile(r"^User=(?!__|\$|%)(\S+)", re.MULTILINE)


def _tracked() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return [p for p in out.stdout.splitlines() if not p.startswith(FROZEN)]


def _text(path: str) -> str:
    try:
        return (REPO_ROOT / path).read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
        return ""


@pytest.fixture(scope="module")
def tracked() -> list[str]:
    files = _tracked()
    assert files, "git ls-files returned nothing — the scan would pass vacuously"
    return files


class TestNothingIsPinnedToOneOperatorsMachine:
    """AC4. A path under someone's home directory is a machine, not a config."""

    def test_no_shipped_file_carries_a_personal_home_path(self, tracked: list[str]):
        """Everything a user reads or runs. Test *source* is exempt below — it
        invents fake home paths (`/home/someone`, `/home/operator`) as inputs on
        purpose, and an allowlist of invented names would only grow."""
        candidates = [p for p in tracked if not p.startswith("tests/")]
        assert candidates, "nothing to scan — this check would pass vacuously"

        offenders = {
            path: sorted({m.group(0) for m in PERSONAL_HOME.finditer(_text(path))})
            for path in candidates
        }
        offenders = {p: hits for p, hits in offenders.items() if hits}

        assert not offenders, f"personal home paths in tracked files: {offenders}"

    def test_no_test_fixture_carries_a_personal_home_path(self, tracked: list[str]):
        """Fixtures under `tests/**/fixtures/` are captured real-world output, not
        invented input — `kilocode_help/help-0.22.0.txt` shipped the maintainer's
        cwd as the `--workspace` default. Captures get scrubbed; nothing asserts
        on the path, only on its shape."""
        fixtures = [p for p in tracked if "/fixtures/" in p]
        assert fixtures, "no fixtures found — this check would pass vacuously"

        offenders = {
            path: sorted({m.group(0) for m in PERSONAL_HOME.finditer(_text(path))})
            for path in fixtures
        }
        offenders = {p: hits for p, hits in offenders.items() if hits}

        assert not offenders, f"personal home paths in captured fixtures: {offenders}"

    def test_no_systemd_unit_hardcodes_an_account(self):
        units = sorted(REPO_ROOT.glob("systemd/*.service"))
        assert units, "no systemd units found — this check would pass vacuously"

        offenders = {u.name: LITERAL_SYSTEMD_USER.findall(u.read_text()) for u in units}
        offenders = {n: hits for n, hits in offenders.items() if hits}

        assert not offenders, f"systemd units naming a literal account: {offenders}"


class TestNoScriptClaimsSuccessItDidNotEarn:
    """AC2. The failure mode is a pipeline step that goes green having done nothing."""

    def test_no_tracked_script_announces_a_simulated_deployment(self, tracked: list[str]):
        scripts = [p for p in tracked if p.startswith("scripts/")]
        assert scripts, "no scripts tracked — this check would pass vacuously"

        offenders = [
            p
            for p in scripts
            if re.search(r"simulat\w*\s+success|success\w*\s+simulat", _text(p), re.I)
        ]

        assert not offenders, f"scripts printing simulated success: {offenders}"

    @pytest.mark.parametrize(
        "path",
        [
            "scripts/deploy.sh",  # exit 0 without deploying
            "scripts/seed-staging.sh",  # faked success against the removed v1 API
            "scripts/fix_workspace_env.py",  # AC3 — one-off e2e repair from 2025
            "scripts/test-websocket.py",  # AC3 — personal LAN host, removed /ws route
        ],
    )
    def test_the_known_dead_script_is_gone(self, path: str):
        assert not (REPO_ROOT / path).exists(), f"{path} is still here"


class TestUnitsCanActuallyRunWhatTheyName:
    """`scripts/health-check.sh` was tracked 100644 while every other tracked
    script was 100755. The generated unit `ExecStart`s it, so a fresh clone
    installed a timer that fails 203/EXEC on its first fire — and nothing in the
    tree chmods it."""

    def test_every_path_a_systemd_unit_execs_is_tracked_executable(self):
        units = sorted(REPO_ROOT.glob("systemd/*.service"))
        assert units, "no systemd units found — this check would pass vacuously"

        execs = re.compile(r"^ExecStart=(?:__CF_ROOT__|[^\s]*?)/(scripts/\S+)", re.M)
        named = {m for u in units for m in execs.findall(u.read_text())}
        assert named, "no ExecStart script paths parsed — the regex broke"

        modes = subprocess.run(
            ["git", "ls-files", "-s", *sorted(named)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        assert len(modes) == len(named), f"a unit ExecStarts an untracked path: {named}"

        not_executable = [line for line in modes if not line.startswith("100755")]
        assert (
            not not_executable
        ), f"systemd ExecStart targets are not tracked executable: {not_executable}"


class TestInstallersPointAtFilesThatExist:
    """`install-systemd-service.sh` installed `codeframe-staging.service` for months
    after that unit was deleted — it could only ever abort. An installer that cannot
    succeed is the same defect class as a script that always succeeds."""

    def test_every_systemd_path_a_script_names_resolves(self, tracked: list[str]):
        named = re.compile(r"systemd/[\w.-]+\.(?:service|timer)")
        missing = {}
        for path in (p for p in tracked if p.startswith("scripts/")):
            gone = sorted({u for u in named.findall(_text(path)) if not (REPO_ROOT / u).exists()})
            if gone:
                missing[path] = gone

        assert not missing, f"scripts install units that do not exist: {missing}"


class TestScratchArtifactsAreOutOfTheWay:
    """AC1. What someone cloning the repo sees first."""

    @pytest.mark.parametrize(
        "path",
        ["test_config_manual.py", "tests/test_issues.md", "claudedocs"],
    )
    def test_the_artifact_is_no_longer_at_its_old_location(self, path: str):
        assert not (REPO_ROOT / path).exists(), f"{path} is still in place"

    def test_no_demo_walkthroughs_litter_the_repo_root(self):
        strays = sorted(p.name for p in REPO_ROOT.glob("demo-*.md"))

        assert not strays, f"demo walkthroughs still at the repo root: {strays}"

    def test_playwright_last_run_is_not_tracked(self, tracked: list[str]):
        """It overrode its own `.gitignore` entry and permanently reported 'failed'."""
        assert not [
            p for p in tracked if p.startswith("test-results/")
        ], "test-results/ is gitignored but something in it is still tracked"


class TestDeployWorkflowDoesNotResolveDependenciesFreely:
    """AC5. Already true since the container rebuild — pinned so it stays true."""

    def test_no_workflow_installs_project_dependencies_without_the_lockfile(self):
        """`npm install -g <cli>` is a tool install with no lockfile to honour and
        is out of scope; resolving *this project's* dependencies must use `npm ci`
        so a deploy cannot silently pick up a different tree than CI tested."""
        workflows = sorted((REPO_ROOT / ".github/workflows").glob("*.yml"))
        assert workflows, "no workflows found — this check would pass vacuously"

        project_install = re.compile(r"\bnpm install\b(?!\s+(?:-g\b|--global\b))")
        offenders = sorted(w.name for w in workflows if project_install.search(w.read_text()))

        assert not offenders, f"workflows using `npm install` instead of `npm ci`: {offenders}"
