"""Three ways the PROOF9 merge gate let a merge through it should block (#1276).

Every test asserts the gate's outcome (which requirements block), never what a
mock was called with: a fail-closed `except Exception` downstream would absorb
an in-band mock assertion and turn a broken test green (#1254).
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone

import pytest

from codeframe.core.proof import ledger
from codeframe.core.proof.evidence import list_blocking_requirements
from codeframe.core.proof.models import (
    Gate,
    Obligation,
    Requirement,
    RequirementScope,
    ReqStatus,
    Severity,
    Source,
    Waiver,
)
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def ws(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("x = 1\n")
    w = create_or_load_workspace(repo)
    ledger.init_proof_tables(w)
    return w


def _req(req_id="REQ-0001", files=("app.py",), status=ReqStatus.OPEN, waiver=None):
    return Requirement(
        id=req_id, title=f"t {req_id}", description="d", severity=Severity.HIGH,
        source=Source.QA, scope=RequirementScope(files=list(files)),
        obligations=[Obligation(gate=Gate.UNIT)], evidence_rules=[], status=status,
        waiver=waiver, created_at=datetime.now(timezone.utc),
    )


def _ids(reqs):
    return sorted(r.id for r in reqs)


# ---------------------------------------------------------------------------
# 1. Expired waivers
# ---------------------------------------------------------------------------


class TestExpiredWaivers:
    def test_a_lapsed_waiver_blocks_the_merge(self, ws):
        today = datetime.now(timezone.utc).date()
        ledger.save_requirement(ws, _req(
            status=ReqStatus.WAIVED,
            waiver=Waiver(reason="later", expires=today - timedelta(days=19)),
        ))
        assert _ids(list_blocking_requirements(ws)) == ["REQ-0001"]

    def test_the_check_is_read_only(self, ws):
        """The gate reports it; reverting the status stays cf proof's job."""
        today = datetime.now(timezone.utc).date()
        ledger.save_requirement(ws, _req(
            status=ReqStatus.WAIVED, waiver=Waiver(reason="r", expires=today - timedelta(days=1)),
        ))
        list_blocking_requirements(ws)
        assert ledger.get_requirement(ws, "REQ-0001").status == ReqStatus.WAIVED

    def test_a_waiver_expiring_today_still_holds(self, ws):
        """The expiry date is the waiver's last valid day (#952)."""
        today = datetime.now(timezone.utc).date()
        ledger.save_requirement(ws, _req(
            status=ReqStatus.WAIVED, waiver=Waiver(reason="r", expires=today),
        ))
        assert list_blocking_requirements(ws) == []

    def test_an_open_ended_waiver_still_holds(self, ws):
        ledger.save_requirement(ws, _req(status=ReqStatus.WAIVED, waiver=Waiver(reason="r")))
        assert list_blocking_requirements(ws) == []

    def test_a_lapsed_waiver_out_of_the_prs_scope_does_not_block(self, ws):
        ledger.save_requirement(ws, _req(
            files=("other.py",), status=ReqStatus.WAIVED,
            waiver=Waiver(reason="r", expires=date(2020, 1, 1)),
        ))
        assert list_blocking_requirements(ws, RequirementScope(files=["app.py"])) == []


# ---------------------------------------------------------------------------
# 2. 0.9.3-era absolute paths stored in scope.files
# ---------------------------------------------------------------------------


def _store_raw_scope(ws, req_id, files):
    """Write scope.files straight into the row, as 0.9.3 did (no #1258 classifier)."""
    import json

    conn = sqlite3.connect(str(ws.db_path))
    conn.execute(
        "UPDATE proof_requirements SET scope = ? WHERE id = ?",
        (json.dumps({"routes": [], "components": [], "apis": [], "files": files, "tags": []}), req_id),
    )
    conn.commit()
    conn.close()
    ledger._scope_normalized_workspaces.discard(ws.id)


class TestLegacyAbsoluteScopes:
    def test_an_absolute_path_inside_the_workspace_is_relativized(self, ws):
        ledger.save_requirement(ws, _req())
        _store_raw_scope(ws, "REQ-0001", [str(ws.repo_path / "app.py")])

        blocking = list_blocking_requirements(ws, RequirementScope(files=["app.py"]))

        assert _ids(blocking) == ["REQ-0001"]  # scoped to app.py, so it blocks
        assert ledger.get_requirement(ws, "REQ-0001").scope.files == ["app.py"]

    @pytest.mark.parametrize("stored", [
        "C:/repo/app.py", "~/repo/app.py", "file:///repo/app.py",
        # Spellings the scope classifier treats as absolute (internal review).
        "file:/repo/app.py", "C:repo/app.py", "\\\\share\\app.py",
    ])
    def test_an_unmatchable_absolute_path_fails_closed(self, ws, stored):
        """It can never equal a repo-relative path, so it must block every PR."""
        ledger.save_requirement(ws, _req())
        _store_raw_scope(ws, "REQ-0001", [stored])

        blocking = list_blocking_requirements(ws, RequirementScope(files=["README.md"]))

        assert _ids(blocking) == ["REQ-0001"]

    def test_a_comma_in_a_stored_filename_is_not_a_separator(self, ws):
        """One stored entry is one path (codex review): the capture classifier
        would split `a,b.py` into route `a` plus file `b.py`."""
        (ws.repo_path / "a,b.py").write_text("")
        ledger.save_requirement(ws, _req())
        _store_raw_scope(ws, "REQ-0001", [str(ws.repo_path / "a,b.py")])

        blocking = list_blocking_requirements(ws, RequirementScope(files=["a,b.py"]))

        assert _ids(blocking) == ["REQ-0001"]
        assert ledger.get_requirement(ws, "REQ-0001").scope.files == ["a,b.py"]

    def test_relative_paths_are_left_alone(self, ws):
        ledger.save_requirement(ws, _req(files=("src/x.py",)))
        _store_raw_scope(ws, "REQ-0001", ["src/x.py"])
        list_blocking_requirements(ws)
        assert ledger.get_requirement(ws, "REQ-0001").scope.files == ["src/x.py"]


# ---------------------------------------------------------------------------
# 3. GitHub's 3000-file cap and count mismatches
# ---------------------------------------------------------------------------


class _FakeGitHub:
    """Answers like GitHub: /pulls/{n} reports changed_files, /files pages it,
    and silently stops at the cap."""

    def __init__(self, changed_files: int, listed: int):
        self.changed_files, self.listed = changed_files, listed

    async def __call__(self, method, endpoint, json_data=None):
        m = re.search(r"/pulls/(\d+)/files\?per_page=100&page=(\d+)", endpoint)
        if m:
            page = int(m.group(2))
            start = (page - 1) * 100
            return [{"filename": f"f{i}.py"} for i in range(start, min(start + 100, self.listed))]
        return {"number": 7, "changed_files": self.changed_files}


def _files(changed_files, listed):
    from codeframe.git.github_integration import GitHubIntegration

    gh = GitHubIntegration(token="t", repo="o/r")
    gh._make_request = _FakeGitHub(changed_files, listed)
    try:
        return asyncio.run(gh.get_pr_files(7, include_previous=True, require_complete=True))
    finally:
        asyncio.run(gh.close())


class TestIncompleteFileLists:
    def test_a_complete_list_is_returned(self):
        assert len(_files(changed_files=250, listed=250)) == 250

    def test_a_list_at_the_cap_is_refused(self):
        from codeframe.git.github_integration import IncompletePRFilesError

        with pytest.raises(IncompletePRFilesError):
            _files(changed_files=4200, listed=3000)

    def test_a_list_at_the_cap_is_refused_even_when_the_count_agrees(self):
        """At exactly 3000 the list cannot be told apart from a truncated one
        (changed_files may itself be capped), so refuse rather than trust it."""
        from codeframe.git.github_integration import IncompletePRFilesError

        with pytest.raises(IncompletePRFilesError):
            _files(changed_files=3000, listed=3000)

    def test_a_count_that_disagrees_with_the_pr_is_refused(self):
        from codeframe.git.github_integration import IncompletePRFilesError

        with pytest.raises(IncompletePRFilesError):
            _files(changed_files=120, listed=100)

    def test_the_cli_gate_falls_back_to_the_whole_workspace(self, ws, monkeypatch):
        """End to end: a truncated list must not let an unlisted file's
        requirement escape the gate."""
        from unittest.mock import patch

        from codeframe.cli import pr_commands
        from codeframe.git.github_integration import GitHubIntegration

        ledger.save_requirement(ws, _req(files=("zz_beyond_the_cap.py",)))
        real_init = GitHubIntegration.__init__

        def init(self, *a, **kw):
            real_init(self, *a, **kw)
            self._make_request = _FakeGitHub(changed_files=4200, listed=3000)

        with patch.object(GitHubIntegration, "__init__", init), patch(
            "codeframe.core.github_integration_config.resolve_github_credentials",
            return_value=("t", "o/r"),
        ):
            scope = pr_commands._resolve_pr_scope(ws, 7)

        assert scope is None  # match-everything
        assert _ids(list_blocking_requirements(ws, scope)) == ["REQ-0001"]
