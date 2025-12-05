"""API tests for workspace cleanup on project creation failure (Issue #7).

These tests verify that the API endpoint properly cleans up both database
and filesystem when workspace creation fails.

TDD approach: RED → GREEN → REFACTOR
"""

import pytest


@pytest.mark.unit
class TestWorkspaceCleanupAPI:
    """Test workspace cleanup through API endpoint."""

    def test_workspace_cleanup_after_git_clone_failure(self, api_client):
        """Test that workspace directory is cleaned up when git clone fails.

        Scenario: User provides invalid git URL, workspace creation fails,
        both database record and workspace directory should be removed.

        This is the KEY test that verifies the fix for Issue #7.
        """
        # ACT: Try to create project with invalid git URL
        response = api_client.post(
            "/api/projects",
            json={
                "name": "invalid-git-project",
                "description": "Test project",
                "source_type": "git_remote",
                "source_location": "https://github.com/nonexistent/invalid-repo-12345.git",
                "source_branch": "main",
            },
        )

        # ASSERT: API should return 500 error
        assert response.status_code == 500
        assert "Workspace creation failed" in response.json()["detail"]

        # Verify database record was deleted
        projects = api_client.get("/api/projects").json()["projects"]
        assert len(projects) == 0, "Database record should be deleted"

        # KEY ASSERTION: Verify workspace directory doesn't exist
        # This verifies that the API endpoint explicitly cleaned up the workspace
        workspace_root = api_client.app.state.workspace_manager.workspace_root
        orphaned_dirs = list(workspace_root.glob("*"))
        assert len(orphaned_dirs) == 0, (
            f"Orphaned workspace directories found: {orphaned_dirs}. "
            "API endpoint should explicitly clean up workspace on failure."
        )

    def test_workspace_cleanup_when_manager_cleanup_fails(self, api_client):
        """Test that API endpoint explicitly cleans up if WorkspaceManager cleanup fails.

        This is the critical test for Issue #7: what if WorkspaceManager's
        internal cleanup (shutil.rmtree) fails or is interrupted?

        The API endpoint should have explicit cleanup as a safety net.
        """
        from unittest.mock import patch

        # ARRANGE: Mock workspace_manager.create_workspace to:
        # 1. Create workspace directory (simulating partial creation)
        # 2. Fail to clean it up (simulating interrupted/failed cleanup)
        # 3. Raise RuntimeError (to trigger API's exception handler)

        original_create = api_client.app.state.workspace_manager.create_workspace
        workspace_root = api_client.app.state.workspace_manager.workspace_root

        def mock_create_with_partial_workspace(**kwargs):
            """Simulate workspace creation failure with incomplete cleanup."""
            project_id = kwargs.get('project_id')

            # Create partial workspace (simulating partial creation before failure)
            workspace_path = workspace_root / str(project_id)
            workspace_path.mkdir(parents=True, exist_ok=True)
            (workspace_path / "partial.txt").write_text("partial content")

            # Simulate failure WITHOUT cleaning up the workspace
            # (This simulates WorkspaceManager's cleanup failing or being interrupted)
            raise RuntimeError("Git clone failed, cleanup also failed")

        with patch.object(
            api_client.app.state.workspace_manager,
            'create_workspace',
            side_effect=mock_create_with_partial_workspace
        ):
            # ACT: Try to create project (will fail)
            response = api_client.post(
                "/api/projects",
                json={
                    "name": "cleanup-test",
                    "description": "Test project",
                    "source_type": "empty",
                },
            )

            # ASSERT: API should return 500 error
            assert response.status_code == 500
            assert "Workspace creation failed" in response.json()["detail"]

            # Verify database record was deleted
            projects = api_client.get("/api/projects").json()["projects"]
            assert len(projects) == 0, "Database record should be deleted"

            # KEY ASSERTION: Verify workspace was cleaned up by API endpoint
            # This is the fix we're testing: API endpoint should explicitly
            # clean up workspace even if WorkspaceManager's cleanup failed
            orphaned_dirs = list(workspace_root.glob("*"))
            assert len(orphaned_dirs) == 0, (
                f"Orphaned workspace directories found: {orphaned_dirs}. "
                "API endpoint should explicitly clean up workspace even when "
                "WorkspaceManager's cleanup fails."
            )

    def test_no_cleanup_on_successful_creation(self, api_client):
        """Test that successful project creation doesn't trigger cleanup.

        Sanity check: Normal project creation should work and leave workspace intact.
        """
        # ACT: Create project successfully
        response = api_client.post(
            "/api/projects",
            json={
                "name": "success-test",
                "description": "Test project",
                "source_type": "empty",
            },
        )

        # ASSERT: Success
        assert response.status_code == 201
        project_id = response.json()["id"]

        # Verify database record exists
        projects = api_client.get("/api/projects").json()["projects"]
        assert len(projects) == 1
        assert projects[0]["id"] == project_id

        # Verify workspace exists (NOT cleaned up)
        workspace_root = api_client.app.state.workspace_manager.workspace_root
        workspace_path = workspace_root / str(project_id)
        assert workspace_path.exists(), "Workspace should exist after successful creation"
        assert (workspace_path / ".git").exists(), "Git repo should be initialized"
