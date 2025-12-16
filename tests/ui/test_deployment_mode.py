"""Tests for deployment mode validation."""

import pytest
import os
import tempfile
import shutil
from pathlib import Path
from fastapi.testclient import TestClient
from codeframe.persistence.database import Database


@pytest.fixture
def test_client_hosted():
    """Test client with HOSTED mode."""
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test.db"
    workspace_root = temp_dir / "workspaces"

    # Save original environment
    original_db_path = os.environ.get("DATABASE_PATH")
    original_workspace_root = os.environ.get("WORKSPACE_ROOT")
    original_deployment_mode = os.environ.get("CODEFRAME_DEPLOYMENT_MODE")

    # Set environment variables
    os.environ["DATABASE_PATH"] = str(db_path)
    os.environ["WORKSPACE_ROOT"] = str(workspace_root)
    os.environ["CODEFRAME_DEPLOYMENT_MODE"] = "hosted"

    # Reload server module to pick up new environment
    from codeframe.ui import server
    from importlib import reload

    reload(server)

    # Initialize database
    db = Database(db_path)
    db.initialize()
    server.app.state.db = db

    # Initialize workspace manager
    from codeframe.workspace import WorkspaceManager

    server.app.state.workspace_manager = WorkspaceManager(workspace_root)

    client = TestClient(server.app)

    yield client

    # Cleanup
    db.close()
    shutil.rmtree(temp_dir, ignore_errors=True)

    # Restore original environment
    if original_db_path is not None:
        os.environ["DATABASE_PATH"] = original_db_path
    else:
        os.environ.pop("DATABASE_PATH", None)

    if original_workspace_root is not None:
        os.environ["WORKSPACE_ROOT"] = original_workspace_root
    else:
        os.environ.pop("WORKSPACE_ROOT", None)

    if original_deployment_mode is not None:
        os.environ["CODEFRAME_DEPLOYMENT_MODE"] = original_deployment_mode
    else:
        os.environ.pop("CODEFRAME_DEPLOYMENT_MODE", None)


@pytest.fixture
def test_client_self_hosted():
    """Test client with SELF_HOSTED mode."""
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test.db"
    workspace_root = temp_dir / "workspaces"

    # Save original environment
    original_db_path = os.environ.get("DATABASE_PATH")
    original_workspace_root = os.environ.get("WORKSPACE_ROOT")
    original_deployment_mode = os.environ.get("CODEFRAME_DEPLOYMENT_MODE")

    # Set environment variables
    os.environ["DATABASE_PATH"] = str(db_path)
    os.environ["WORKSPACE_ROOT"] = str(workspace_root)
    os.environ["CODEFRAME_DEPLOYMENT_MODE"] = "self_hosted"

    # Reload server module to pick up new environment
    from codeframe.ui import server
    from importlib import reload

    reload(server)

    # Initialize database
    db = Database(db_path)
    db.initialize()
    server.app.state.db = db

    # Initialize workspace manager
    from codeframe.workspace import WorkspaceManager

    server.app.state.workspace_manager = WorkspaceManager(workspace_root)

    client = TestClient(server.app)

    yield client

    # Cleanup
    db.close()
    shutil.rmtree(temp_dir, ignore_errors=True)

    # Restore original environment
    if original_db_path is not None:
        os.environ["DATABASE_PATH"] = original_db_path
    else:
        os.environ.pop("DATABASE_PATH", None)

    if original_workspace_root is not None:
        os.environ["WORKSPACE_ROOT"] = original_workspace_root
    else:
        os.environ.pop("WORKSPACE_ROOT", None)

    if original_deployment_mode is not None:
        os.environ["CODEFRAME_DEPLOYMENT_MODE"] = original_deployment_mode
    else:
        os.environ.pop("CODEFRAME_DEPLOYMENT_MODE", None)


def test_hosted_mode_blocks_local_path(test_client_hosted):
    """Verify hosted mode rejects local_path source type."""
    response = test_client_hosted.post(
        "/api/projects",
        json={
            "name": "Test",
            "description": "Test",
            "source_type": "local_path",
            "source_location": "/home/user/project",
        },
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
            "source_location": "https://github.com/user/repo.git",
        },
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
            "source_location": "/tmp/test",
        },
    )

    # Should not be blocked with 403
    assert response.status_code != 403
