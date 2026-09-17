"""#1194 — the web-ui lockfile is fine; one npm version is not.

The issue was filed believing `web-ui/package-lock.json` was internally
inconsistent — that it recorded `@napi-rs/wasm-runtime@1.2.3` with an older
release's dependency set. Measured against the registry, it does not: 1.2.3's
`dependencies` really is just `{"@tybys/wasm-util":"^0.10.3"}`, the `@emnapi/*`
packages arrive as *peerDependencies*, and every `@emnapi/*` entry in the lock
matches what the registry publishes — `@emnapi/core@1.10.0` pins
`@emnapi/wasi-threads: "1.2.1"` exactly, which is what is recorded.

What actually differs is npm. Run against the untouched lock (`npm install`, then
`npm ci`), 10.8.2, 11.0.0, 11.4.0, 11.5.0, 11.7.0, 11.9.0, 11.10.0 and 11.19.0 all
round-trip cleanly; only **11.6.2** produces a lock that `npm ci` then rejects,
because its `npm install` drops the peer-installed optional `@emnapi/core` and
`@emnapi/runtime` entries and `npm ci` correctly demands them back. libc is not a
variable — glibc and musl behave identically at the same npm.

So there is no lockfile to repair. What is worth pinning is that the constraint
stays *written down*, in the two places someone lands when this next goes wrong.
"""

import json

import pytest

from pathlib import Path

pytestmark = pytest.mark.v2

REPO = Path(__file__).resolve().parents[2]
PACKAGE_JSON = REPO / "web-ui" / "package.json"
NPMRC = REPO / "web-ui" / ".npmrc"
CLAUDE_MD = REPO / "CLAUDE.md"
DEPLOY_README = REPO / "deploy" / "README.md"

# Measured, not guessed. Only 11.6.x is affected: 11.5.0 and 11.7.0 both pass.
KNOWN_BAD_NPM = "11.6.2"
# The docs name the whole excluded minor line rather than the one build tested.
KNOWN_BAD_NPM_LINE = "11.6"


def _engines() -> dict:
    return json.loads(PACKAGE_JSON.read_text()).get("engines", {})


def test_the_npm_range_is_declared():
    """Without it npm says nothing at all when a bad version rewrites the lock."""
    assert "npm" in _engines(), (
        "web-ui/package.json declares no `engines.npm`, so nothing records which "
        f"npm versions may generate the lockfile — npm {KNOWN_BAD_NPM} corrupts it"
    )


def test_the_range_excludes_the_measured_bad_version_and_admits_its_neighbours():
    """A range is only worth having if it draws the line where the data does.

    11.5.0 and 11.7.0 both round-trip cleanly, so excluding them would be
    superstition; 11.6.2 does not, so admitting it would be decoration.
    """
    npm_range = _engines()["npm"]

    assert not _allows(npm_range, KNOWN_BAD_NPM), (
        f"engines.npm is {npm_range!r}, which still admits npm {KNOWN_BAD_NPM} — "
        "the one version measured to corrupt the lockfile"
    )
    for good in ("10.8.2", "11.5.0", "11.7.0", "11.19.0"):
        assert _allows(npm_range, good), (
            f"engines.npm is {npm_range!r}, which rejects npm {good} — measured "
            "to round-trip the lockfile cleanly, so this over-blocks"
        )


def _parts(version: str) -> tuple:
    """`"11.10.0"` -> `(11, 10, 0)`, so 11.10 sorts above 11.6 rather than below.

    Every version this compares is a plain npm `X.Y.Z`, so a tuple of ints is the
    whole of the semantics — no need to reach for a version-parsing library.
    """
    return tuple(int(n) for n in version.split("."))


def _allows(npm_range: str, version: str) -> bool:
    """Evaluate an npm engines range of the shape `>=A <B || >=C`."""
    ops = {
        ">=": lambda a, b: a >= b,
        "<=": lambda a, b: a <= b,
        "<": lambda a, b: a < b,
        ">": lambda a, b: a > b,
        "=": lambda a, b: a == b,
    }

    def satisfies(constraint: str) -> bool:
        # `>=`/`<=` before `>`/`<`, or the two-character forms mis-parse.
        for op, compare in ops.items():
            if constraint.startswith(op):
                return compare(_parts(version), _parts(constraint[len(op) :]))
        raise AssertionError(f"unparsed engines constraint {constraint!r}")

    return any(
        all(satisfies(c) for c in clause.split() if c.strip())
        for clause in npm_range.split("||")
    )


def test_the_range_evaluator_itself_is_not_lying():
    """The assertions above are only as good as this parser."""
    assert _parts("11.10.0") > _parts("11.6.2"), "numeric ordering, not string"
    assert _allows(">=1.0.0", "1.0.0") and not _allows(">=1.0.1", "1.0.0")
    assert _allows(">=1.0.0 <2.0.0", "1.5.0") and not _allows(">=1.0.0 <2.0.0", "2.0.0")
    assert _allows(">=1.0.0 <2.0.0 || >=3.0.0", "3.1.0")
    assert not _allows(">=1.0.0 <2.0.0 || >=3.0.0", "2.5.0")


def test_the_node_range_admits_the_version_ci_and_the_image_run():
    """CI's NODE_VERSION and web-ui/Dockerfile are both on Node 20."""
    node_range = _engines().get("node", "")
    assert "20" in node_range, (
        f"engines.node is {node_range!r}; CI and web-ui/Dockerfile both run Node 20, "
        "so this would declare the project's own build environment unsupported"
    )


def test_engine_strict_is_not_reintroduced():
    """It is the obvious next step, and it breaks the build (verified, #1194).

    `engine-strict=true` validates *every* package's engines, not just the root's,
    and `@testing-library/jest-dom@7.0.1` already requires node >=22 while CI and
    web-ui/Dockerfile run Node 20 — so it turns `npm ci` into `npm error notsup`
    on the environment the project actually builds in. `engines` stays advisory
    here on purpose: an `EBADENGINE` warning naming the npm version is the signal,
    and the docs carry the rest.
    """
    if not NPMRC.exists():
        return
    assert "engine-strict=true" not in NPMRC.read_text(), (
        "web-ui/.npmrc sets engine-strict=true, which fails `npm ci` on Node 20 via "
        "@testing-library/jest-dom's node>=22 requirement — see #1194"
    )


@pytest.mark.parametrize("doc", [CLAUDE_MD, DEPLOY_README], ids=lambda p: p.name)
def test_the_docs_name_the_npm_version_not_the_lockfile(doc: Path):
    """The original diagnosis is written into both docs, and it is wrong.

    Left uncorrected it tells the next reader that *any* regenerated lock fails
    `npm ci`, which sends them to hand-prune a lockfile that does not need it —
    the practice the issue itself says must not become the house pattern.
    """
    text = doc.read_text()
    assert f"npm {KNOWN_BAD_NPM_LINE}" in text, (
        f"{doc.name} does not name npm {KNOWN_BAD_NPM_LINE}.x as the actual cause, so "
        "it still reads as though the committed lockfile were the problem"
    )


# #1223 — the lock is a fixed point only under the npm that generated it.
# Measured: npm 11.19.0 rewrites 0 lines; 10.8.2 and every 11.x below it
# rewrite 108 — the 36 `libc` fields 11.19 records on platform-specific
# optional packages. Benign, but shaped exactly like the #1194 bug, so the
# generating npm has to be written down where a contributor will look.
LOCK_NPM_LINE = "11.19"


def test_the_lock_generation_npm_is_stated_beside_engines():
    pkg = json.loads(PACKAGE_JSON.read_text())
    note = pkg.get("//", "")
    assert LOCK_NPM_LINE in note and "libc" in note, note


def test_the_lock_generation_npm_is_stated_in_claude_md():
    text = (REPO / "CLAUDE.md").read_text()
    assert f"npm >= {LOCK_NPM_LINE}" in text and "#1223" in text
    assert "libc" in text, "the churn must be characterised, not just named"
