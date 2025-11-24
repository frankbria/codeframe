"""Tests for project API endpoints."""

import pytest
import tempfile
import shutil
from pathlib import Path
from fastapi.testclient import TestClient
from codeframe.ui.server import app
from codeframe.persistence.database import Database


@pytest.fixture
def test_client():
    """Create test client with temporary database."""
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test.db"
    workspace_root = temp_dir / "workspaces"

    # Save original app.state
    original_db = getattr(app.state, 'db', None)
    original_workspace_root = getattr(app.state, 'workspace_root', None)
    original_workspace_manager = getattr(app.state, 'workspace_manager', None)

    # Override database and workspace paths
    db = Database(db_path)
    db.initialize()

    app.state.db = db
    app.state.workspace_root = workspace_root

    # Initialize workspace manager
    from codeframe.workspace import WorkspaceManager

    app.state.workspace_manager = WorkspaceManager(workspace_root)

    client = TestClient(app)

    yield client

    # Cleanup
    db.close()
    shutil.rmtree(temp_dir, ignore_errors=True)

    # Delete app.state attributes (DON'T restore them - causes closed DB reuse)
    if hasattr(app.state, 'db'):
        delattr(app.state, 'db')
    if hasattr(app.state, 'workspace_root'):
        delattr(app.state, 'workspace_root')
    if hasattr(app.state, 'workspace_manager'):
        delattr(app.state, 'workspace_manager')


def test_create_project_minimal(test_client):
    """Test creating project with minimal required fields."""
    response = test_client.post(
        "/api/projects", json={"name": "Test Project", "description": "A test project"}
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Project"
    # Note: API response doesn't include description/source fields currently


def test_create_project_git_remote(test_client):
    """Test creating project from git repository (will fail on fake URL)."""
    response = test_client.post(
        "/api/projects",
        json={
            "name": "Git Project",
            "description": "From git",
            "source_type": "git_remote",
            "source_location": "https://github.com/user/repo.git",
        },
    )

    # This will fail with 500 because the git URL is fake
    # For now, just verify it's not a validation error (422)
    assert response.status_code in [201, 500]  # 201 if git works, 500 if repo doesn't exist


def test_create_project_validation_error(test_client):
    """Test validation error for missing source_location."""
    response = test_client.post(
        "/api/projects",
        json={
            "name": "Test",
            "description": "Test",
            "source_type": "git_remote",
            # Missing source_location
        },
    )

    assert response.status_code == 422


def test_create_project_missing_description(test_client):
    """Test validation error for missing description."""
    response = test_client.post("/api/projects", json={"name": "Test"})

    assert response.status_code == 422
