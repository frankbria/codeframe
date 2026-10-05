"""Deleting a workspace forgets who connected its GitHub repo (#1370).

`DELETE /api/v2/workspaces/{id}` removed the registry row but left the
workspace's entry in `~/.codeframe/github_connection_owners.json`, so a later
workspace at the same path inherited it, and `resolve_background_pat` would
read the previous owner's stored PAT. Uses the #720 owner-scope fixture
(auth on, users 1 and 2, workspace "alpha" owned by user 1).
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from codeframe.core import credentials
from codeframe.core.github_integration_config import connection_owner, record_connection_owner
from tests.ui import test_workspace_registry_owner_scope as _scope

pytestmark = pytest.mark.v2

app_with_user_a_workspace = _scope.app_with_user_a_workspace
ALPHA = SimpleNamespace(repo_path=Path("/home/a/projects/alpha"))


@pytest.fixture(autouse=True)
def owners_store(tmp_path, monkeypatch):
    monkeypatch.setattr(credentials, "DEFAULT_STORAGE_DIR", tmp_path / "store")
    record_connection_owner(ALPHA, 1)
    assert connection_owner(ALPHA) == 1


def test_deleting_the_workspace_forgets_its_connection_owner(app_with_user_a_workspace):
    app, workspace_id = app_with_user_a_workspace
    with TestClient(app) as client:
        r = client.delete(f"/api/v2/workspaces/{workspace_id}", headers=_scope._bearer(1))
    assert r.status_code == 204, r.text
    assert connection_owner(ALPHA) is None


def test_a_refused_delete_forgets_nothing(app_with_user_a_workspace):
    """User 2 cannot deregister user 1's workspace (#720), so the owner record
    must survive the 404 too."""
    app, workspace_id = app_with_user_a_workspace
    with TestClient(app) as client:
        r = client.delete(f"/api/v2/workspaces/{workspace_id}", headers=_scope._bearer(2))
    assert r.status_code == 404, r.text
    assert connection_owner(ALPHA) == 1
