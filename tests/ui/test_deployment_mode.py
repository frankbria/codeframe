"""Tests for deployment mode validation."""
import pytest
import os
import tempfile
import shutil
from pathlib import Path
from fastapi.testclient import TestClient
from codeframe.ui.server import app
from codeframe.persistence.database import Database


@pytest.fixture
def test_client_hosted():
    """Test client with HOSTED mode."""
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test.db"
    workspace_root = temp_dir / "workspaces"

    # Override database and workspace paths
    db = Database(db_path)
    db.initialize()

    app.state.db = db
    app.state.workspace_root = workspace_root

    # Initialize workspace manager
    from codeframe.workspace import WorkspaceManager
    app.state.workspace_manager = WorkspaceManager(workspace_root)

    os.environ["CODEFRAME_DEPLOYMENT_MODE"] = "hosted"
    client = TestClient(app)
    
    yield client
    
    # Cleanup
    del os.environ["CODEFRAME_DEPLOYMENT_MODE"]
    db.close()
    shutil.rmtree(temp_dir)


@pytest.fixture
def test_client_self_hosted():
    """Test client with SELF_HOSTED mode."""
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test.db"
    workspace_root = temp_dir / "workspaces"

    # Override database and workspace paths
    db = Database(db_path)
    db.initialize()

    app.state.db = db
    app.state.workspace_root = workspace_root

    # Initialize workspace manager
    from codeframe.workspace import WorkspaceManager
    app.state.workspace_manager = WorkspaceManager(workspace_root)

    os.environ["CODEFRAME_DEPLOYMENT_MODE"] = "self_hosted"
    client = TestClient(app)
    
    yield client
    
    # Cleanup
    del os.environ["CODEFRAME_DEPLOYMENT_MODE"]
    db.close()
    shutil.rmtree(temp_dir)


def test_hosted_mode_blocks_local_path(test_client_hosted):
    """Verify hosted mode rejects local_path source type."""
    response = test_client_hosted.post(
        "/api/projects",
        json={
            "name": "Test",
            "description": "Test",
            "source_type": "local_path",
            "source_location": "/home/user/project"
        }
    )

    assert response.status_code == 403
    assert "not available in hosted mode" in response.json()["detail"]


def test_hosted_mode_allows_git_remote(test_client_hosted):
    """Verify hosted mode allows git_remote."""
    response = test_client_hosted.post(
        "/api/projects",
        json={
            "name": "Test",
            "description": "Test",
            "source_type": "git_remote",
            "source_location": "https://github.com/user/repo.git"
        }
    )

    # Should not be blocked (may fail for other reasons, but not 403)
    assert response.status_code != 403


def test_self_hosted_allows_all_sources(test_client_self_hosted):
    """Verify self-hosted mode allows all source types."""
    # Test local_path is allowed
    response = test_client_self_hosted.post(
        "/api/projects",
        json={
            "name": "Test",
            "description": "Test",
            "source_type": "local_path",
            "source_location": "/tmp/test"
        }
    )

    # Should not be blocked with 403
    assert response.status_code != 403