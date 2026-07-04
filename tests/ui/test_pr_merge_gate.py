"""Tests for the server-side PROOF9 merge gate on POST /api/v2/pr/{n}/merge (#731).

Merge must be blocked while open (non-waived) requirements exist, unless the
caller supplies an explicit, audited override. GitHubIntegration is mocked so
no real GitHub calls are made.
"""

import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.core.proof.ledger import (
    get_pr_merge_override,
    init_proof_tables,
    save_requirement,
)
from codeframe.core.proof.models import (
    Gate,
    Obligation,
    ReqStatus,
    Requirement,
    RequirementScope,
    Severity,
    Source,
    Waiver,
)
from codeframe.git.github_integration import MergeResult

pytestmark = pytest.mark.v2


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def test_workspace():
    temp_dir = Path(tempfile.mkdtemp())
    workspace_path = temp_dir / "test_ws"
    workspace_path.mkdir(parents=True, exist_ok=True)

    from codeframe.core.workspace import create_or_load_workspace

    workspace = create_or_load_workspace(workspace_path)
    init_proof_tables(workspace)

    yield workspace

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_client(test_workspace):
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import pr_v2

    app = FastAPI()
    app.include_router(pr_v2.router)
    app.dependency_overrides[get_v2_workspace] = lambda: test_workspace
    return TestClient(app, raise_server_exceptions=False)


def _make_mock_client() -> MagicMock:
    client = MagicMock()
    client.merge_pull_request = AsyncMock(
        return_value=MergeResult(sha="abc123", merged=True, message="Merged")
    )
    client.close = AsyncMock()
    return client


def _req(req_id: str, status: ReqStatus = ReqStatus.OPEN, waiver: Waiver | None = None) -> Requirement:
    return Requirement(
        id=req_id,
        title=f"requirement {req_id}",
        description="d",
        severity=Severity.LOW,
        source=Source.QA,
        scope=RequirementScope(files=["x.py"]),
        obligations=[Obligation(gate=Gate.UNIT)],
        evidence_rules=[],
        status=status,
        waiver=waiver,
        created_at=datetime.now(timezone.utc),
    )


def _merge(client, body: dict | None = None):
    return client.post("/api/v2/pr/42/merge", json=body or {"method": "squash"})


# ── Tests ─────────────────────────────────────────────────────────────────


class TestMergeGate:
    def test_open_requirements_block_merge(self, test_client, test_workspace):
        save_requirement(test_workspace, _req("REQ-1"))

        mock = _make_mock_client()
        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock):
            resp = _merge(test_client)

        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert "REQ-1" in str(detail)
        mock.merge_pull_request.assert_not_called()

    def test_no_requirements_merges(self, test_client):
        mock = _make_mock_client()
        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock):
            resp = _merge(test_client)

        assert resp.status_code == 200
        assert resp.json()["merged"] is True
        mock.merge_pull_request.assert_called_once()

    def test_satisfied_and_waived_do_not_block(self, test_client, test_workspace):
        save_requirement(test_workspace, _req("REQ-S", status=ReqStatus.SATISFIED))
        save_requirement(
            test_workspace,
            _req("REQ-W", status=ReqStatus.WAIVED, waiver=Waiver(reason="known", approved_by="qa")),
        )

        mock = _make_mock_client()
        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock):
            resp = _merge(test_client)

        assert resp.status_code == 200
        mock.merge_pull_request.assert_called_once()

    def test_override_with_reason_merges_and_records_audit(self, test_client, test_workspace):
        save_requirement(test_workspace, _req("REQ-1"))

        mock = _make_mock_client()
        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock):
            resp = _merge(
                test_client,
                {"method": "squash", "override": True, "override_reason": "hotfix, gate is stale"},
            )

        assert resp.status_code == 200
        mock.merge_pull_request.assert_called_once()

        record = get_pr_merge_override(test_workspace, 42)
        assert record is not None
        assert record["reason"] == "hotfix, gate is stale"
        assert record["overridden_at"]
        assert any(b["id"] == "REQ-1" for b in record["bypassed"])

    def test_override_without_reason_rejected(self, test_client, test_workspace):
        save_requirement(test_workspace, _req("REQ-1"))

        mock = _make_mock_client()
        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock):
            resp = _merge(test_client, {"method": "squash", "override": True})

        assert resp.status_code == 422
        mock.merge_pull_request.assert_not_called()

    def test_ledger_failure_blocks_merge(self, test_client):
        mock = _make_mock_client()
        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock), patch(
            "codeframe.core.proof.ledger.list_requirements",
            side_effect=RuntimeError("db corrupt"),
        ):
            resp = _merge(test_client)

        assert resp.status_code == 500
        mock.merge_pull_request.assert_not_called()

    def test_failed_merge_writes_no_override_record(self, test_client, test_workspace):
        """Override audit must only exist for merges that actually happened."""
        from codeframe.git.github_integration import GitHubAPIError

        save_requirement(test_workspace, _req("REQ-1"))

        mock = _make_mock_client()
        mock.merge_pull_request = AsyncMock(side_effect=GitHubAPIError(405, "not mergeable"))
        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock):
            resp = _merge(
                test_client,
                {"method": "squash", "override": True, "override_reason": "hotfix"},
            )

        assert resp.status_code == 400
        assert get_pr_merge_override(test_workspace, 42) is None

    def test_unmerged_result_writes_no_override_record(self, test_client, test_workspace):
        save_requirement(test_workspace, _req("REQ-1"))

        mock = _make_mock_client()
        mock.merge_pull_request = AsyncMock(
            return_value=MergeResult(sha=None, merged=False, message="nope")
        )
        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock):
            resp = _merge(
                test_client,
                {"method": "squash", "override": True, "override_reason": "hotfix"},
            )

        assert resp.status_code == 200
        assert resp.json()["merged"] is False
        assert get_pr_merge_override(test_workspace, 42) is None

    def test_clean_merge_writes_no_override_record(self, test_client, test_workspace):
        mock = _make_mock_client()
        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock):
            resp = _merge(test_client)

        assert resp.status_code == 200
        assert get_pr_merge_override(test_workspace, 42) is None
