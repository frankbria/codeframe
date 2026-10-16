"""PROOF9 ratchet — lock currently-passing tests in as obligations (#1467).

A fresh workspace has an empty ledger, so there is nothing for ``cf proof run``
to enforce. The ratchet runs the project's test suite once and turns every
test that passes today into a requirement with one UNIT obligation, so a test
that passes now cannot silently stop passing. It invents no criteria: it only
records behaviour that already holds.

Each test is locked by its function name, because that is how the runner
enforces an evidence rule (#1401) — so a name is locked only when the runner's
own verdict on its cases would be a pass.
"""

import shutil
import sqlite3
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from codeframe.core import gates as core_gates
from codeframe.core.agent_env import build_agent_env
from codeframe.core.proof import ledger
from codeframe.core.proof.models import (
    EvidenceRule,
    Gate,
    Obligation,
    Requirement,
    RequirementScope,
    Severity,
    Source,
)
from codeframe.core.workspace import Workspace

# A whole suite, not one test: the gate runner's 5 minutes is too short.
SUITE_TIMEOUT_SECONDS = 1800

# Scope for a test whose covered files are unknown: the repository root, which
# `scope._files_intersect` treats as covering every file (fail closed).
WHOLE_REPO = "."

_COV_ARGS = ["--cov=.", "--cov-context=test", "--cov-report=", "--cov-fail-under=0"]


class RatchetError(Exception):
    """The suite gave nothing to lock in. ``no_tests`` separates "nothing was
    collected" from "the suite could not run"."""

    def __init__(self, message: str, *, no_tests: bool = False):
        super().__init__(message)
        self.no_tests = no_tests


@dataclass
class SuiteResult:
    """One run of the project's suite, reduced to what the ratchet needs."""

    #: Test name → repo-relative files it covers (``["."]`` when unknown).
    passing: dict[str, list[str]] = field(default_factory=dict)
    failed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    #: Passing, but not ``test_``-prefixed, so no evidence rule can enforce it.
    unenforceable: list[str] = field(default_factory=list)
    #: False when per-test coverage was unavailable and every scope is the whole repo.
    per_file_scope: bool = True


@dataclass
class RatchetResult:
    #: Test name → scope files, for the tests newly locked (or, on a dry run,
    #: that would be).
    locked: dict[str, list[str]] = field(default_factory=dict)
    req_ids: list[str] = field(default_factory=list)
    already_locked: list[str] = field(default_factory=list)


def run_suite(
    repo_path: Path,
    *,
    path_glob: Optional[str] = None,
    sandbox_root: Optional[Path] = None,
) -> SuiteResult:
    """Run the project's pytest suite once and classify every test.

    ``sandbox_root`` is the workspace whose ``.codeframe/`` holds the sandboxed
    HOME; when None (no workspace yet) a throwaway one is used, so a dry run or
    a failed run leaves nothing behind.

    Raises:
        RatchetError: nothing was collected, or the suite could not run.
    """
    repo_path = repo_path.resolve()
    # --path only filters which tests are locked; the whole suite still runs,
    # because the runner judges a name by every case of it in the suite.
    within: Optional[list[Path]] = None
    if path_glob:
        try:
            within = [
                m.resolve() for m in repo_path.glob(path_glob)
                if m.resolve().is_relative_to(repo_path)
            ]
        except (ValueError, NotImplementedError) as exc:
            raise RatchetError(f"Invalid --path {path_glob!r}: {exc}") from exc
        if not within:
            raise RatchetError(
                f"No tests found: --path {path_glob!r} matches nothing in the repository.",
                no_tests=True,
            )

    if not shutil.which("uv") and not shutil.which("pytest"):
        raise RatchetError("The test suite could not run: pytest was not found.")
    base = ["uv", "run", "pytest"] if shutil.which("uv") else ["pytest"]

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        env = build_agent_env(sandbox_root or tmp_path)
        env["COVERAGE_FILE"] = str(tmp_path / "coverage.db")
        report = tmp_path / "report.xml"
        # --maxfail=0 overrides a project's -x, which would leave tests unrun.
        # xunit1 records each case's file, which --path filters on. No cache
        # provider, so a dry run leaves no .pytest_cache behind.
        cmd = base + [
            "--maxfail=0", "-p", "no:cacheprovider",
            "-o", "junit_family=xunit1", f"--junitxml={report}",
        ]

        def _pytest(extra: list[str]) -> subprocess.CompletedProcess[str]:
            try:
                return subprocess.run(
                    cmd + extra,
                    cwd=repo_path,
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=SUITE_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired as exc:
                raise RatchetError(
                    f"The test suite could not run: timed out after {SUITE_TIMEOUT_SECONDS}s."
                ) from exc

        result = _pytest(_COV_ARGS)
        per_file = True
        if result.returncode == 4 and "unrecognized arguments: --cov" in (result.stderr or ""):
            per_file = False
            result = _pytest([])

        if core_gates._tool_is_missing(result.returncode, result.stderr, {"pytest"}):
            raise RatchetError(
                "The test suite could not run: pytest is not in the project's dependencies."
            )
        if result.returncode == 5:
            raise RatchetError("No tests found: pytest collected nothing.", no_tests=True)
        if result.returncode not in (0, 1) or not report.exists():
            tail = "\n".join(((result.stdout or "") + (result.stderr or "")).strip().splitlines()[-15:])
            raise RatchetError(
                f"The test suite could not run (pytest exit {result.returncode}):\n{tail}"
            )

        suite = _classify(report, repo_path, within)
        coverage = _covered_files(tmp_path / "coverage.db", repo_path) if per_file else None

    suite.per_file_scope = coverage is not None
    for name in suite.passing:
        suite.passing[name] = sorted((coverage or {}).get(name, ())) or [WHOLE_REPO]
    return suite


def _classify(report: Path, repo_path: Path, within: Optional[list[Path]]) -> SuiteResult:
    """Group JUnit cases by test name and judge each name as the runner will.

    With ``within`` (the --path matches), only names with a case in one of
    those files or directories are reported — but still judged on all their
    cases, so one failing elsewhere is not locked.
    """
    try:
        cases = list(ET.parse(report).getroot().iter("testcase"))
    except ET.ParseError as exc:
        raise RatchetError(f"The test suite could not run: unreadable report ({exc}).") from exc
    if not cases:
        raise RatchetError("No tests found: pytest collected nothing.", no_tests=True)

    by_name: dict[str, list[ET.Element]] = defaultdict(list)
    for case in cases:
        raw = case.get("name", "")
        # `or raw`: a doctest is named `[doctest] mod.fn`, which strips to "".
        by_name[raw.split("[", 1)[0] or raw].append(case)

    def _in_path(case: ET.Element) -> bool:
        f = (repo_path / case.get("file", "")).resolve()
        return any(f.is_relative_to(w) for w in within or ())

    if within is not None:
        by_name = {n: cs for n, cs in by_name.items() if any(_in_path(c) for c in cs)}
        if not by_name:
            raise RatchetError("No tests found under --path.", no_tests=True)

    suite = SuiteResult()
    for name in sorted(by_name):
        verdict = core_gates.cases_verdict(by_name[name])
        if verdict == "failed":
            suite.failed.append(name)
        elif verdict == "skipped":
            suite.skipped.append(name)
        elif not name.startswith("test_"):
            suite.unenforceable.append(name)
        else:
            suite.passing[name] = []
    return suite


def _covered_files(data_file: Path, repo_path: Path) -> Optional[dict[str, set[str]]]:
    """Test name → repo-relative files its coverage context touched.

    Reads pytest-cov's ``--cov-context=test`` data directly (coverage's data
    file is SQLite), so CodeFRAME needs no coverage dependency of its own.
    Contexts look like ``tests/test_x.py::TestK::test_m[p]|run``. Missing or
    unreadable data yields None: every test is then scoped to the whole repo,
    and the caller says so.
    """
    if not data_file.exists():
        return None
    try:
        conn = sqlite3.connect(data_file)
        try:
            rows = conn.execute(
                "SELECT c.context, f.path FROM context c "
                "JOIN (SELECT file_id, context_id FROM line_bits "
                "      UNION SELECT DISTINCT file_id, context_id FROM arc) t "
                "  ON t.context_id = c.id "
                "JOIN file f ON f.id = t.file_id"
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return None

    covered: dict[str, set[str]] = defaultdict(set)
    for context, path in rows:
        node = context.rsplit("|", 1)[0].split("[", 1)[0]
        if "::" not in node:
            continue  # the empty context: import-time, not any one test
        test_file, name = node.split("::", 1)[0], node.rsplit("::", 1)[1]
        # repo_path / path: `relative_files = True` stores repo-relative paths,
        # and an absolute one is unchanged by the join.
        for candidate in (repo_path / path, repo_path / test_file):
            try:
                covered[name].add(candidate.resolve().relative_to(repo_path).as_posix())
            except ValueError:
                pass  # outside the repository
    return covered


def lock_in(
    workspace: Optional[Workspace], suite: SuiteResult, *, dry_run: bool = False
) -> RatchetResult:
    """Create one requirement per passing test not already locked in.

    Dedupes on the test name of every existing ``ratchet`` requirement, in any
    status. ``workspace`` may be None only for a dry run in a repository that
    has none yet. A dry run writes nothing.
    """
    existing: set[str] = set()
    if workspace is not None:
        existing = {
            rule.test_id
            for req in ledger.list_requirements(workspace)
            if req.source == Source.RATCHET
            for rule in req.evidence_rules
        }

    result = RatchetResult()
    for name, files in suite.passing.items():
        if name in existing:
            result.already_locked.append(name)
        else:
            result.locked[name] = files
    if dry_run:
        return result
    if workspace is None:
        raise ValueError("lock_in needs a workspace unless dry_run is set")

    for name, files in result.locked.items():
        req = ledger.allocate_requirement(
            workspace, lambda req_id, name=name, files=files: _requirement(req_id, name, files)
        )
        result.req_ids.append(req.id)
    return result


def _requirement(req_id: str, name: str, files: list[str]) -> Requirement:
    return Requirement(
        id=req_id,
        title=f"{name} keeps passing",
        description=(
            f"Locked in by `cf proof ratchet`: `{name}` passed when the suite "
            "was ratcheted, so it must keep passing."
        ),
        severity=Severity.MEDIUM,
        source=Source.RATCHET,
        scope=RequirementScope(files=list(files)),
        obligations=[Obligation(gate=Gate.UNIT)],
        evidence_rules=[EvidenceRule(test_id=name, must_pass=True, gate=Gate.UNIT)],
        created_at=datetime.now(timezone.utc),
        created_by="ratchet",
    )
