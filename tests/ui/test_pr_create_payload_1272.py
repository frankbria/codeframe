"""The review page's exact Create PR payload is accepted (#1272).

The page sent ``branch: ''`` ("let the backend use the current branch"), which
``CreatePRRequest.branch`` (``min_length=1``) rejects with a 422 before the
handler runs, so Create PR never worked from the web UI. The page now sends the
checked-out branch from git status; this posts that payload, the same shape
``web-ui/src/app/review/page.tsx`` builds, and asserts it reaches GitHub.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.git.github_integration import PRDetails

pytestmark = pytest.mark.v2


@pytest.fixture
def client(tmp_path):
    from codeframe.core.workspace import create_or_load_workspace
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import pr_v2

    ws_path = tmp_path / "ws"
    ws_path.mkdir()
    workspace = create_or_load_workspace(ws_path)
    app = FastAPI()
    app.include_router(pr_v2.router)
    app.dependency_overrides[get_v2_workspace] = lambda: workspace
    return TestClient(app, raise_server_exceptions=False)


def _github():
    gh = MagicMock()
    gh.create_pull_request = AsyncMock(
        return_value=PRDetails(
            number=7, url="https://github.com/o/r/pull/7", state="open", title="T",
            body="B", created_at=datetime.now(timezone.utc), merged_at=None,
            head_branch="feature/x", base_branch="main",
        )
    )
    gh.close = AsyncMock()
    return gh


def test_the_pages_payload_reaches_github(client):
    gh = _github()
    with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=gh):
        # Exactly what review/page.tsx sends: branch, title, body (base defaults).
        resp = client.post("/api/v2/pr", json={"branch": "feature/x", "title": "T", "body": "B"})

    assert resp.status_code == 201, resp.text
    assert resp.json()["number"] == 7
    gh.create_pull_request.assert_awaited_once()
    sent = gh.create_pull_request.await_args.kwargs
    assert (sent["branch"], sent["title"], sent["base"]) == ("feature/x", "T", "main")
    assert sent["body"].startswith("B")  # + the PROOF9 report since #1358


def test_the_old_empty_branch_payload_is_the_422_the_page_used_to_get(client):
    gh = _github()
    with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=gh):
        resp = client.post("/api/v2/pr", json={"branch": "", "title": "T", "body": "B"})

    assert resp.status_code == 422
    gh.create_pull_request.assert_not_awaited()
