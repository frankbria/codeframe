"""Tests for the workspace registry API endpoints (issue #601).

Covers GET /api/v2/workspaces (list), registration on POST, recency tracking +
auto-registration on GET /current, and DELETE deregistration. The registry lives
in the global control-plane DB attached at ``app.state.db``.

Following TDD: tests written first, implementation follows.
"""

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.platform_store.database import Database

pytestmark = pytest.mark.v2


@pytest.fixture
def temp_root():
    root = Path(tempfile.mkdtemp())
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def client(temp_root):
    """TestClient with the workspace_v2 router and a real in-memory control-plane DB."""
    from codeframe.ui.routers import workspace_v2

    app = FastAPI()
    app.include_router(workspace_v2.router)

    db = Database(":memory:")
    db.initialize()
    app.state.db = db

    with TestClient(app, raise_server_exceptions=True) as c:
        c.db = db  # expose for tests that need to pin registry state directly
        yield c


def _make_repo(temp_root: Path, name: str) -> Path:
    repo = temp_root / name
    repo.mkdir(parents=True, exist_ok=True)
    return repo


class TestListWorkspaces:
    def test_list_empty(self, client):
        resp = client.get("/api/v2/workspaces")
        assert resp.status_code == 200
        assert resp.json() == {"workspaces": []}

    def test_post_registers_and_list_returns_it(self, client, temp_root):
        repo = _make_repo(temp_root, "alpha")

        post = client.post("/api/v2/workspaces", json={"repo_path": str(repo)})
        assert post.status_code == 201

        resp = client.get("/api/v2/workspaces")
        assert resp.status_code == 200
        workspaces = resp.json()["workspaces"]
        assert len(workspaces) == 1
        entry = workspaces[0]
        assert entry["repo_path"] == str(repo.resolve())
        assert entry["name"] == "alpha"
        assert entry["path_exists"] is True
        assert "id" in entry and "created_at" in entry and "last_opened_at" in entry

    def test_path_exists_false_for_deleted_dir(self, client, temp_root):
        repo = _make_repo(temp_root, "beta")
        client.post("/api/v2/workspaces", json={"repo_path": str(repo)})

        # Remove the directory from disk after registration.
        shutil.rmtree(repo)

        resp = client.get("/api/v2/workspaces")
        entry = resp.json()["workspaces"][0]
        assert entry["path_exists"] is False

    def test_list_sorted_by_last_opened_desc(self, client, temp_root):
        a = _make_repo(temp_root, "a")
        b = _make_repo(temp_root, "b")
        client.post("/api/v2/workspaces", json={"repo_path": str(a)})
        client.post("/api/v2/workspaces", json={"repo_path": str(b)})

        # Pin both to fixed past timestamps so the upcoming /current bump on 'a'
        # is unambiguously the newest, regardless of sub-second POST timing.
        client.db.conn.execute(
            "UPDATE workspaces_registry SET last_opened_at = '2000-01-01T00:00:00+00:00'"
        )
        client.db.conn.commit()

        # Touch 'a' again so it becomes the most recently opened.
        client.get("/api/v2/workspaces/current", params={"workspace_path": str(a)})

        workspaces = client.get("/api/v2/workspaces").json()["workspaces"]
        assert workspaces[0]["repo_path"] == str(a.resolve())


class TestPatchRefreshesRegistry:
    def test_tech_stack_edit_updates_registry_metadata(self, client, temp_root):
        repo = _make_repo(temp_root, "zeta")
        client.post("/api/v2/workspaces", json={"repo_path": str(repo)})

        resp = client.patch(
            "/api/v2/workspaces/current",
            params={"workspace_path": str(repo)},
            json={"tech_stack": "Python with FastAPI"},
        )
        assert resp.status_code == 200

        entry = client.get("/api/v2/workspaces").json()["workspaces"][0]
        assert entry["tech_stack"] == "Python with FastAPI"


class TestCurrentTracksAccess:
    def test_current_auto_registers_untracked_workspace(self, client, temp_root):
        """A workspace opened directly (not via POST) becomes tracked."""
        repo = _make_repo(temp_root, "gamma")
        # Initialize the workspace on disk without going through the registry-aware
        # POST path: use core.workspace directly.
        from codeframe.core.workspace import create_or_load_workspace

        create_or_load_workspace(repo)

        # Sanity: not yet in registry.
        assert client.get("/api/v2/workspaces").json()["workspaces"] == []

        resp = client.get(
            "/api/v2/workspaces/current", params={"workspace_path": str(repo)}
        )
        assert resp.status_code == 200

        workspaces = client.get("/api/v2/workspaces").json()["workspaces"]
        assert len(workspaces) == 1
        assert workspaces[0]["repo_path"] == str(repo.resolve())


class TestRegistryUnavailable:
    """When no control-plane DB is attached, the registry endpoints must signal
    unavailability (503) rather than a misleading empty-but-successful response —
    clients treat a 200 as authoritative and would wipe their local fallback.
    """

    @pytest.fixture
    def client_no_db(self):
        from codeframe.ui.routers import workspace_v2

        app = FastAPI()
        app.include_router(workspace_v2.router)
        # Deliberately do NOT set app.state.db.
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c

    def test_list_returns_503_without_registry(self, client_no_db):
        assert client_no_db.get("/api/v2/workspaces").status_code == 503

    def test_delete_returns_503_without_registry(self, client_no_db):
        assert client_no_db.delete("/api/v2/workspaces/anything").status_code == 503


class TestDeleteWorkspace:
    def test_delete_existing_returns_204(self, client, temp_root):
        repo = _make_repo(temp_root, "delta")
        client.post("/api/v2/workspaces", json={"repo_path": str(repo)})
        entry = client.get("/api/v2/workspaces").json()["workspaces"][0]

        resp = client.delete(f"/api/v2/workspaces/{entry['id']}")
        assert resp.status_code == 204

        assert client.get("/api/v2/workspaces").json()["workspaces"] == []

    def test_delete_missing_returns_404(self, client):
        resp = client.delete("/api/v2/workspaces/does-not-exist")
        assert resp.status_code == 404

    def test_delete_does_not_remove_disk_state(self, client, temp_root):
        repo = _make_repo(temp_root, "epsilon")
        client.post("/api/v2/workspaces", json={"repo_path": str(repo)})
        entry = client.get("/api/v2/workspaces").json()["workspaces"][0]

        client.delete(f"/api/v2/workspaces/{entry['id']}")

        # .codeframe state dir must survive deregistration.
        assert (repo / ".codeframe").exists()
