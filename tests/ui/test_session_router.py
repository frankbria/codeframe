"""Tests for session router endpoints.

Tests session state retrieval with phase and step information.
Following TDD principles - these tests define the expected API contract.
"""

import pytest
import os
import sys
import tempfile
import shutil
from pathlib import Path
from fastapi.testclient import TestClient

from tests.conftest import create_test_jwt_token


@pytest.fixture
def test_client():
    """Create test client with temporary database and authentication."""
    from fastapi import FastAPI

    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test.db"
    workspace_root = temp_dir / "workspaces"

    # Save original environment
    original_db_path = os.environ.get("DATABASE_PATH")
    original_workspace_root = os.environ.get("WORKSPACE_ROOT")

    # Set environment variables FIRST
    os.environ["DATABASE_PATH"] = str(db_path)
    os.environ["WORKSPACE_ROOT"] = str(workspace_root)

    # Force fresh imports by removing cached modules
    # Save original modules so we can restore them after test
    saved_modules = {k: v for k, v in sys.modules.items() if k.startswith("codeframe")}
    for mod in list(saved_modules.keys()):
        del sys.modules[mod]

    # Now import with fresh state
    from codeframe.ui.routers import session as session_router
    from codeframe.ui.routers import projects as projects_router
    from codeframe.ui.routers import discovery as discovery_router
    from codeframe.persistence.database import Database
    from codeframe.ui.dependencies import get_db as original_get_db

    # Create a new FastAPI app to avoid duplicate route issues
    app = FastAPI()
    app.include_router(session_router.router)
    app.include_router(projects_router.router)
    app.include_router(discovery_router.router)

    # Initialize database
    db = Database(db_path)
    db.initialize()
    app.state.db = db

    # Override the database dependency
    def get_test_db():
        return db

    app.dependency_overrides[original_get_db] = get_test_db

    # Create test user (user_id=1)
    db.conn.execute(
        """
        INSERT OR REPLACE INTO users (
            id, email, name, hashed_password,
            is_active, is_superuser, is_verified, email_verified
        )
        VALUES (1, 'test@example.com', 'Test User', '!DISABLED!', 1, 0, 1, 1)
        """
    )
    db.conn.commit()

    # Initialize workspace manager
    from codeframe.workspace import WorkspaceManager

    app.state.workspace_manager = WorkspaceManager(workspace_root)

    # Override auth dependency to return test user
    from codeframe.auth.dependencies import get_current_user
    from codeframe.auth.models import User

    async def get_test_user():
        return User(id=1, email="test@example.com", hashed_password="!DISABLED!")

    app.dependency_overrides[get_current_user] = get_test_user

    # Create test client with authentication headers
    auth_token = create_test_jwt_token(user_id=1)
    client = TestClient(app, headers={"Authorization": f"Bearer {auth_token}"})

    # Attach db to client for test access
    client.db = db

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

    # Restore original modules to avoid affecting other tests
    # First clear any modules we imported during this test
    test_modules = [k for k in sys.modules.keys() if k.startswith("codeframe")]
    for mod in test_modules:
        del sys.modules[mod]
    # Then restore the original modules
    sys.modules.update(saved_modules)


class TestSessionEndpointPhaseAndStep:
    """Tests for phase and step fields in session response."""

    def test_get_session_state_includes_phase(self, test_client):
        """Session state should include phase field."""
        # Create a project
        response = test_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test description"}
        )
        assert response.status_code == 201
        project_id = response.json()["id"]

        # Get session state
        response = test_client.get(f"/api/projects/{project_id}/session")
        assert response.status_code == 200

        data = response.json()
        assert "phase" in data
        assert data["phase"] == "discovery"  # Default phase

    def test_get_session_state_includes_step(self, test_client):
        """Session state should include step object with current, total, description."""
        response = test_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test"}
        )
        project_id = response.json()["id"]

        response = test_client.get(f"/api/projects/{project_id}/session")
        data = response.json()

        assert "step" in data
        assert "current" in data["step"]
        assert "total" in data["step"]
        assert "description" in data["step"]
        assert isinstance(data["step"]["current"], int)
        assert isinstance(data["step"]["total"], int)
        assert isinstance(data["step"]["description"], str)

    def test_get_session_state_discovery_phase_values(self, test_client):
        """Discovery phase should have correct step configuration."""
        response = test_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test"}
        )
        project_id = response.json()["id"]

        response = test_client.get(f"/api/projects/{project_id}/session")
        data = response.json()

        assert data["phase"] == "discovery"
        assert data["step"]["total"] == 4
        assert data["step"]["description"] == "Discovery Phase"
        assert data["step"]["current"] == 1  # Default to step 1

    def test_get_session_state_planning_phase_values(self, test_client):
        """Planning phase should have correct step configuration."""
        # Create project
        response = test_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test"}
        )
        project_id = response.json()["id"]

        # Update phase directly in database
        test_client.db.update_project(project_id, {"phase": "planning"})

        response = test_client.get(f"/api/projects/{project_id}/session")
        data = response.json()

        assert data["phase"] == "planning"
        assert data["step"]["total"] == 4
        assert data["step"]["description"] == "Planning Phase"

    def test_get_session_state_active_phase_values(self, test_client):
        """Active phase should have correct step configuration."""
        response = test_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test"}
        )
        project_id = response.json()["id"]

        test_client.db.update_project(project_id, {"phase": "active"})

        response = test_client.get(f"/api/projects/{project_id}/session")
        data = response.json()

        assert data["phase"] == "active"
        assert data["step"]["total"] == 5
        assert data["step"]["description"] == "Development Phase"

    def test_get_session_state_review_phase_values(self, test_client):
        """Review phase should have correct step configuration."""
        response = test_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test"}
        )
        project_id = response.json()["id"]

        test_client.db.update_project(project_id, {"phase": "review"})

        response = test_client.get(f"/api/projects/{project_id}/session")
        data = response.json()

        assert data["phase"] == "review"
        assert data["step"]["total"] == 3
        assert data["step"]["description"] == "Review Phase"

    def test_get_session_state_complete_phase_values(self, test_client):
        """Complete phase should have correct step configuration."""
        response = test_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test"}
        )
        project_id = response.json()["id"]

        test_client.db.update_project(project_id, {"phase": "complete"})

        response = test_client.get(f"/api/projects/{project_id}/session")
        data = response.json()

        assert data["phase"] == "complete"
        assert data["step"]["total"] == 1
        assert data["step"]["description"] == "Complete"


class TestSessionEndpointNoWorkspace:
    """Tests for session state when project has no workspace."""

    def test_get_session_state_no_workspace_includes_phase(self, test_client):
        """Session with no workspace should still include phase and step."""
        # Create project - it won't have workspace_path initially
        response = test_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test"}
        )
        project_id = response.json()["id"]

        # Clear workspace path to simulate no workspace
        test_client.db.update_project(project_id, {"workspace_path": ""})

        response = test_client.get(f"/api/projects/{project_id}/session")
        data = response.json()

        # Should still have phase and step even without workspace
        assert "phase" in data
        assert "step" in data
        assert data["phase"] == "discovery"


class TestSessionEndpointAuthorization:
    """Tests for session endpoint authorization."""

    @pytest.mark.skip(reason="Test requires real auth which is overridden by fixture")
    def test_get_session_state_unauthorized_user(self, test_client):
        """Non-owner should get 403 for session access.

        Note: This test is skipped because the fixture overrides get_current_user
        to always return user 1. Authorization logic is tested in integration tests.
        """
        # Create project as user 1
        response = test_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test"}
        )
        project_id = response.json()["id"]

        # Create user 2 and get their token
        test_client.db.conn.execute(
            """
            INSERT INTO users (
                id, email, name, hashed_password,
                is_active, is_superuser, is_verified, email_verified
            )
            VALUES (2, 'other@example.com', 'Other User', '!DISABLED!', 1, 0, 1, 1)
            """
        )
        test_client.db.conn.commit()

        other_token = create_test_jwt_token(user_id=2)

        # Try to access project 1's session with user 2's token
        response = test_client.get(
            f"/api/projects/{project_id}/session",
            headers={"Authorization": f"Bearer {other_token}"}
        )

        assert response.status_code == 403

    def test_get_session_state_not_found(self, test_client):
        """Non-existent project should return 404."""
        response = test_client.get("/api/projects/99999/session")
        assert response.status_code == 404


class TestSessionResponseFormat:
    """Tests for complete session response structure."""

    def test_session_response_complete_structure(self, test_client):
        """Session response should have all required fields."""
        response = test_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test"}
        )
        project_id = response.json()["id"]

        response = test_client.get(f"/api/projects/{project_id}/session")
        data = response.json()

        # Existing fields
        assert "last_session" in data
        assert "next_actions" in data
        assert "progress_pct" in data
        assert "active_blockers" in data

        # New phase/step fields
        assert "phase" in data
        assert "step" in data

        # Validate last_session structure
        assert "summary" in data["last_session"]
        assert "timestamp" in data["last_session"]

        # Validate step structure
        assert "current" in data["step"]
        assert "total" in data["step"]
        assert "description" in data["step"]

    def test_session_response_types(self, test_client):
        """Session response fields should have correct types."""
        response = test_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test"}
        )
        project_id = response.json()["id"]

        response = test_client.get(f"/api/projects/{project_id}/session")
        data = response.json()

        # Type checks
        assert isinstance(data["last_session"], dict)
        assert isinstance(data["next_actions"], list)
        assert isinstance(data["progress_pct"], (int, float))
        assert isinstance(data["active_blockers"], list)
        assert isinstance(data["phase"], str)
        assert isinstance(data["step"], dict)
        assert isinstance(data["step"]["current"], int)
        assert isinstance(data["step"]["total"], int)
        assert isinstance(data["step"]["description"], str)
