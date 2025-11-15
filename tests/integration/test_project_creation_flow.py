"""Integration tests for full project creation flow."""

import pytest
import tempfile
import shutil
from pathlib import Path
from codeframe.persistence.database import Database
from codeframe.workspace import WorkspaceManager
from codeframe.ui.models import SourceType


@pytest.fixture
def integration_env():
    """Set up integration test environment."""
    temp_dir = Path(tempfile.mkdtemp())

    db_path = temp_dir / "test.db"
    workspace_root = temp_dir / "workspaces"

    db = Database(db_path)
    db.initialize()
    workspace_manager = WorkspaceManager(workspace_root)

    yield {"db": db, "workspace_manager": workspace_manager, "temp_dir": temp_dir}

    db.close()
    shutil.rmtree(temp_dir)


def test_create_empty_project_end_to_end(integration_env):
    """Test full flow: create empty project with database + workspace."""
    db = integration_env["db"]
    workspace_manager = integration_env["workspace_manager"]

    # Step 1: Create project in database
    project_id = db.create_project(
        name="Test Project", description="Integration test", source_type="empty", workspace_path=""
    )

    # Step 2: Create workspace
    workspace_path = workspace_manager.create_workspace(
        project_id=project_id, source_type=SourceType.EMPTY
    )

    # Step 3: Update project with workspace path
    db.update_project(project_id, {"workspace_path": str(workspace_path), "git_initialized": True})

    # Step 4: Verify project state
    project = db.get_project(project_id)

    assert project["name"] == "Test Project"
    assert project["description"] == "Integration test"
    assert project["source_type"] == "empty"
    assert project["workspace_path"] == str(workspace_path)
    assert project["git_initialized"] == 1  # SQLite stores boolean as 1/0

    # Step 5: Verify workspace exists
    assert workspace_path.exists()
    assert (workspace_path / ".git").exists()


def test_create_project_rollback_on_failure(integration_env):
    """Test rollback when workspace creation fails."""
    db = integration_env["db"]
    workspace_manager = integration_env["workspace_manager"]

    # Create project
    project_id = db.create_project(
        name="Test",
        description="Test",
        source_type="git_remote",
        source_location="invalid-url",
        workspace_path="",
    )

    # Try to create workspace (should fail)
    with pytest.raises(Exception):
        workspace_manager.create_workspace(
            project_id=project_id, source_type=SourceType.GIT_REMOTE, source_location="invalid-url"
        )

    # Cleanup: delete project
    db.delete_project(project_id)

    # Verify project deleted
    project = db.get_project(project_id)
    assert project is None
