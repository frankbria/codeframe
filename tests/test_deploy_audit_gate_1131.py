"""#1131 — the deploy's npm audit gate, and the decision behind its level.

`deploy.yml` ran `npm audit --audit-level=critical`, so nothing below critical
could block a deploy. That is how six high-severity advisories accumulated in
`web-ui` unnoticed until #1124 went looking for them.

**The decision, recorded here because a PR comment is not durable.** Four
advisories were open when this was written:

    brace-expansion  high  GHSA-3jxr-9vmj-r5cp / -mh99-v99m-4gvg / -rgw5-rvv9-x895
    js-yaml          high  GHSA-h67p-54hq-rp68 / -52cp-r559-cp3m / -5p4m-2wfm-xmqj
    nanoid           high  GHSA-2v37-7h3g-55p8
    @babel/core      low   GHSA-4x5r-pxfx-6jf8

All four were **fixed, not accepted** — every one had `fixAvailable: true` and
no `effects`, so `npm audit fix` resolved them inside the existing major
versions. `npm test` (1280 tests) and `npm run build` both pass on the result.
There is therefore no allowlist and no review date to carry: an allowlist entry
would have been a record of a risk nobody is taking.

They are all dev/build-time dependencies. That is why they went quiet, not why
they are harmless — build-time code runs on a CI runner with repository
credentials in scope.
"""

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY = REPO_ROOT / ".github" / "workflows" / "deploy.yml"

AUDIT_RE = re.compile(r"npm audit --audit-level=(\w+)")

#: npm's severity ladder, weakest gate first.
LEVELS = ["info", "low", "moderate", "high", "critical"]


def _audit_levels() -> list[str]:
    return AUDIT_RE.findall(DEPLOY.read_text())


def test_both_deploy_jobs_run_an_audit():
    """Staging and production. A gate on one path only is not a gate."""
    assert len(_audit_levels()) == 2, _audit_levels()


def test_the_gate_is_no_weaker_than_high():
    """Expressed as a floor rather than an equality: tightening it further is a
    fine change to make, loosening it is the regression this pins."""
    for level in _audit_levels():
        assert LEVELS.index(level) <= LEVELS.index("high"), (
            f"audit-level={level} is weaker than 'high' — #1131 raised it from "
            "'critical' precisely because criticals are not where the findings were"
        )


def test_the_level_is_explained_where_it_is_set():
    """The next person to see a deploy fail on a fresh advisory needs to know
    the block is deliberate, not a flake."""
    raw = DEPLOY.read_text()
    assert "#1131" in raw


def test_the_audit_runs_before_anything_is_restarted():
    """A gate that fires after PM2 has already been pointed at the new build
    reports a problem that has shipped."""
    raw = DEPLOY.read_text()
    for match in AUDIT_RE.finditer(raw):
        after = raw[match.end() :]
        # Within the same job, the restart must come later in the file.
        assert "pm2 start" in after, "audit appears after the last pm2 start"


class TestTheWebUiLockfileHasNoKnownHighAdvisories:
    """A weak-but-honest offline check.

    `npm audit` needs the network, so a test cannot re-run it. What it can do is
    assert the packages named in the decision above are no longer pinned to the
    versions that carried the advisories — enough to catch a lockfile revert.
    """

    #: The versions this PR shipped, per major line — taken from the lockfile
    #: AFTER the fix, not from the advisory text. My first pass used the
    #: advisories' "patched in" versions, which the pre-fix lockfile already
    #: satisfied, so every assertion passed against the broken state. Verified
    #: the other way this time: these floors fail against main's lockfile.
    FIXED_FLOORS = {
        "brace-expansion": {1: (1, 1, 18), 2: (2, 1, 4), 5: (5, 0, 9)},
        "js-yaml": {3: (3, 15, 1), 4: (4, 3, 1)},
        "nanoid": {3: (3, 3, 18)},
        "@babel/core": {7: (7, 29, 7)},
    }

    def _versions(self, package: str) -> list[tuple[int, ...]]:
        data = json.loads((REPO_ROOT / "web-ui" / "package-lock.json").read_text())
        found = []
        for path, meta in data.get("packages", {}).items():
            if path.rsplit("node_modules/", 1)[-1] == package and "version" in meta:
                parts = meta["version"].split("-")[0].split(".")
                found.append(tuple(int(p) for p in parts))
        return found

    @pytest.mark.parametrize("package", sorted(FIXED_FLOORS))
    def test_no_copy_is_below_the_fixed_version(self, package):
        floors = self.FIXED_FLOORS[package]
        versions = self._versions(package)

        assert versions, f"{package} vanished from the lockfile — check the name"
        # Compared within a major line: a 2.x brace-expansion is a separate
        # release line, not a downgrade of 5.x.
        for version in versions:
            floor = floors.get(version[0])
            assert floor is not None, (
                f"{package} {version} is a major line #1131 never saw — "
                "re-run `npm audit` and extend this table"
            )
            assert version >= floor, f"{package} {version} is below {floor} (#1131)"
