"""#1217 — patch-level Dependabot *security* updates to web-ui merge without a human.

#1210 cost a day of un-deployable staging while the two lockfile bumps that fixed
it sat open and green. The fix is narrow on purpose: npm, ``/web-ui``, a security
advisory, patch-level — and the supply-chain properties that made #1212's lock
diff safe are *checked in code*, not assumed from the semver label. Two halves,
both pinned here: the checker refuses each unsafe shape, and the workflow gates
on the checker plus the Dependabot metadata before it ever calls ``--auto``.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.v2

REPO = Path(__file__).resolve().parents[2]
CHECKER = REPO / "scripts" / "ci" / "lock_diff_is_surgical.py"
WORKFLOW = REPO / ".github" / "workflows" / "dependabot-automerge.yml"


def _lock(packages: dict) -> dict:
    return {"name": "web-ui", "lockfileVersion": 3, "packages": {"": {"name": "web-ui"}, **packages}}


def _entry(version: str, name: str = "js-yaml", **extra) -> dict:
    return {
        "version": version,
        "resolved": f"https://registry.npmjs.org/{name}/-/{name}-{version}.tgz",
        "integrity": f"sha512-{version}",
        **extra,
    }


def _run(tmp_path: Path, base: dict, head: dict) -> subprocess.CompletedProcess:
    b, h = tmp_path / "base.json", tmp_path / "head.json"
    b.write_text(json.dumps(base))
    h.write_text(json.dumps(head))
    return subprocess.run(
        [sys.executable, str(CHECKER), str(b), str(h)], capture_output=True, text=True
    )


BASE = _lock({"node_modules/js-yaml": _entry("4.3.1"), "node_modules/left": _entry("1.0.0", "left")})


class TestTheCheckerRefusesEachUnsafeShape:
    def test_a_surgical_patch_bump_is_safe(self, tmp_path):
        head = _lock({"node_modules/js-yaml": _entry("4.3.2"), "node_modules/left": _entry("1.0.0", "left")})
        res = _run(tmp_path, BASE, head)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "js-yaml 4.3.1 -> 4.3.2" in res.stdout

    def test_an_added_package_is_refused(self, tmp_path):
        head = _lock({**BASE["packages"], "node_modules/evil": _entry("1.0.0", "evil")})
        res = _run(tmp_path, BASE, head)
        assert res.returncode == 1
        assert "added" in res.stdout and "node_modules/evil" in res.stdout

    def test_a_removed_package_is_refused(self, tmp_path):
        head = _lock({"node_modules/js-yaml": _entry("4.3.2")})
        res = _run(tmp_path, BASE, head)
        assert res.returncode == 1
        assert "removed" in res.stdout and "node_modules/left" in res.stdout

    def test_a_new_install_script_is_refused(self, tmp_path):
        head = _lock({**BASE["packages"], "node_modules/js-yaml": _entry("4.3.2", hasInstallScript=True)})
        res = _run(tmp_path, BASE, head)
        assert res.returncode == 1
        assert "install script" in res.stdout

    def test_a_foreign_registry_is_refused(self, tmp_path):
        bad = _entry("4.3.2")
        bad["resolved"] = "https://evil.example/js-yaml-4.3.2.tgz"
        head = _lock({**BASE["packages"], "node_modules/js-yaml": bad})
        res = _run(tmp_path, BASE, head)
        assert res.returncode == 1
        assert "registry.npmjs.org" in res.stdout

    def test_a_minor_or_major_bump_is_refused(self, tmp_path):
        for version in ("4.4.0", "5.0.0"):
            head = _lock({**BASE["packages"], "node_modules/js-yaml": _entry(version)})
            res = _run(tmp_path, BASE, head)
            assert res.returncode == 1, version
            assert "not patch-level" in res.stdout

    def test_a_missing_integrity_is_refused(self, tmp_path):
        bad = _entry("4.3.2")
        del bad["integrity"]
        head = _lock({**BASE["packages"], "node_modules/js-yaml": bad})
        res = _run(tmp_path, BASE, head)
        assert res.returncode == 1
        assert "integrity" in res.stdout

    def test_a_same_version_rewrite_is_refused(self, tmp_path):
        """codex on #1229: a changed `resolved`/`integrity` at the same version
        is a different tarball wearing the same number, not a patch bump."""
        swapped = _entry("4.3.1")
        swapped["integrity"] = "sha512-somethingelse"
        head = _lock({**BASE["packages"], "node_modules/js-yaml": swapped})
        res = _run(tmp_path, BASE, head)
        assert res.returncode == 1
        assert "without a version change" in res.stdout

    def test_a_same_minor_downgrade_is_refused(self, tmp_path):
        base = _lock({**BASE["packages"], "node_modules/js-yaml": _entry("4.3.2")})
        head = _lock({**BASE["packages"], "node_modules/js-yaml": _entry("4.3.1")})
        res = _run(tmp_path, base, head)
        assert res.returncode == 1
        assert "downgrade" in res.stdout

    def test_an_unchanged_lock_is_refused_as_nothing_to_merge(self, tmp_path):
        res = _run(tmp_path, BASE, BASE)
        assert res.returncode == 1
        assert "no package changed" in res.stdout


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def _job() -> dict:
    jobs = _workflow()["jobs"]
    assert len(jobs) == 1, "one job, or the gates below could be split across runs"
    return next(iter(jobs.values()))


def _steps() -> list[dict]:
    return _job()["steps"]


class TestTheWorkflowGatesBeforeItMerges:
    def test_the_job_runs_for_every_push_to_a_dependabot_pr(self):
        """The job must run on a *human* push too — that is when it disarms.
        Gating the whole job on the actor (claude-review on #1229) left an
        armed merge in place for a head nobody re-checked."""
        assert "github.event.pull_request.user.login == 'dependabot[bot]'" in _job()["if"]
        assert "github.actor" not in _job()["if"]

    def test_only_a_dependabot_push_can_arm(self):
        text = WORKFLOW.read_text()
        assert "github.actor == 'dependabot[bot]'" in text

    def test_anything_short_of_armed_disarms(self):
        """`gh pr merge --auto` is persistent, so every run that does not
        (re)arm must explicitly disarm, whatever step stopped it."""
        disarm = [s for s in _steps() if "--disable-auto" in s.get("run", "")]
        assert len(disarm) == 1
        assert "always()" in disarm[0]["if"]
        assert "steps.arm.outcome != 'success'" in disarm[0]["if"]

    def test_a_real_disarm_failure_is_not_swallowed(self):
        """claude-review on #1229: `--disable-auto || echo` hid an API failure
        behind the expected not-armed case. Ask for the state, then disarm
        with no fallback."""
        disarm = next(s for s in _steps() if "--disable-auto" in s.get("run", ""))
        assert "autoMergeRequest" in disarm["run"]
        assert "||" not in disarm["run"]

    def test_event_values_reach_the_shell_through_env(self):
        # GitHub's hardening guide: never interpolate github.event.* into `run:`.
        for step in _steps():
            assert "${{ github.event" not in step.get("run", ""), step.get("name")

    def test_it_runs_on_pull_request_not_pull_request_target(self):
        on = _workflow()[True] if True in _workflow() else _workflow()["on"]
        assert "pull_request" in on
        assert "pull_request_target" not in on

    def test_no_paths_filter_so_every_push_can_disarm(self):
        """A push touching neither package file must still reach the job —
        it is the run that disarms a stale arming (claude-review on #1229)."""
        on = _workflow()[True] if True in _workflow() else _workflow()["on"]
        assert "paths" not in (on["pull_request"] or {})

    def test_runs_for_one_pr_are_serialised_latest_wins(self):
        conc = _workflow()["concurrency"]
        assert "github.event.pull_request.number" in conc["group"]
        assert conc["cancel-in-progress"] is True

    def test_permissions_are_exactly_what_auto_merge_needs(self):
        perms = _workflow().get("permissions") or _job().get("permissions")
        assert perms == {"contents": "write", "pull-requests": "write"}

    def test_fetch_metadata_is_sha_pinned(self):
        uses = [s["uses"] for s in _steps() if "uses" in s and "fetch-metadata" in s["uses"]]
        assert len(uses) == 1
        ref = uses[0].split("@", 1)[1].split()[0]
        assert len(ref) == 40 and all(c in "0123456789abcdef" for c in ref), uses[0]

    def test_every_narrowing_gate_is_present(self):
        text = WORKFLOW.read_text()
        for gate in (
            "package-ecosystem == 'npm'",
            "directory == '/web-ui'",
            "update-type == 'version-update:semver-patch'",
            "alert-state != ''",
        ):
            assert gate in text, f"missing gate: {gate}"

    def test_the_checker_runs_against_the_base_branch_lock(self):
        runs = [s.get("run", "") for s in _steps()]
        assert any("lock_diff_is_surgical.py" in r and "package-lock.json" in r for r in runs)

    def test_merge_is_auto_and_squash(self):
        arm = [s for s in _steps() if s.get("id") == "arm"]
        assert len(arm) == 1
        assert "gh pr merge" in arm[0]["run"] and "--auto" in arm[0]["run"] and "--squash" in arm[0]["run"]


def test_actionlint_accepts_the_workflow():
    # A workflow that fails GitHub's expression pass runs with zero jobs and no
    # logs (#1122); actionlint is the only local check that catches it.
    if not shutil.which("actionlint"):
        # test.yml's workflow-lint job runs actionlint on every workflow in CI.
        pytest.skip("actionlint not installed")
    res = subprocess.run(["actionlint", str(WORKFLOW)], capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr
