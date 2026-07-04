"""Upstream GitHub 401s must never surface as this API's 401 (#734).

The web UI's axios interceptor treats any 401 as CodeFRAME session expiry
(clearToken + redirect to /login), so a bad/revoked PAT must map to 502
UPSTREAM_AUTH_FAILED on every pr_v2 endpoint that talks to GitHub.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.core.proof.ledger import init_proof_tables
from codeframe.git.github_integration import GitHubAPIError

pytestmark = pytest.mark.v2


@pytest.fixture
def test_client(tmp_path):
    from codeframe.core.workspace import create_or_load_workspace
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import pr_v2

    workspace_path = tmp_path / "test_ws"
    workspace_path.mkdir()
    workspace = create_or_load_workspace(workspace_path)
    init_proof_tables(workspace)  # merge endpoint's PROOF9 gate reads the ledger

    app = FastAPI()
    app.include_router(pr_v2.router)
    app.dependency_overrides[get_v2_workspace] = lambda: workspace
    return TestClient(app, raise_server_exceptions=False)


def _client_raising_401() -> MagicMock:
    """Mock GitHubIntegration whose every GitHub call raises a 401."""
    err = GitHubAPIError(401, "Bad credentials")
    client = MagicMock()
    for method in (
        "_make_request",
        "list_pull_requests",
        "get_pr_files",
        "get_pull_request",
        "create_pull_request",
        "merge_pull_request",
        "close_pull_request",
    ):
        setattr(client, method, AsyncMock(side_effect=err))
    client.close = AsyncMock()
    return client


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("GET", "/api/v2/pr", None),
        ("GET", "/api/v2/pr/history", None),
        ("GET", "/api/v2/pr/5/files", None),
        ("GET", "/api/v2/pr/5", None),
        ("POST", "/api/v2/pr", {"branch": "feat", "title": "t"}),
        ("POST", "/api/v2/pr/5/merge", {"method": "squash"}),
        ("POST", "/api/v2/pr/5/close", None),
    ],
)
def test_upstream_401_maps_to_502(test_client, method, url, body):
    with patch(
        "codeframe.ui.routers.pr_v2._get_github_client",
        return_value=_client_raising_401(),
    ):
        resp = test_client.request(method, url, json=body)

    assert resp.status_code == 502, resp.text
    assert resp.json()["detail"]["code"] == "UPSTREAM_AUTH_FAILED"
