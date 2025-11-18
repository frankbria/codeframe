"""Tests for PRD API endpoint (cf-26).

Sprint 2 Foundation Contract:
GET /api/projects/{id}/prd → PRDResponse

Tests follow RED-GREEN-REFACTOR TDD cycle.
"""

import pytest
from datetime import datetime, UTC

from codeframe.ui.server import app


def get_app():
    """Get the current app instance after module reload."""

    return app


@pytest.fixture(scope="function")
def project_with_prd(api_client):
    """Create test project with PRD content.

    Args:
        api_client: FastAPI test client

    Returns:
        Tuple of (project_id, prd_content, generated_at)
    """
    # Create project
    project_id = get_app().state.db.create_project(
        name="Test PRD Project", description="Test PRD Project project"
    )

    # Store PRD content in database
    prd_content = """# Product Requirements Document

## Executive Summary
Build a task management system.

## Problem Statement
Users need better task tracking.

## Features & Requirements
- Create tasks
- Assign tasks
- Track progress
"""

    # Store PRD in memory table
    get_app().state.db.create_memory(
        project_id=project_id, category="prd", key="prd_content", value=prd_content
    )

    # Store metadata
    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    get_app().state.db.create_memory(
        project_id=project_id, category="prd", key="generated_at", value=generated_at
    )

    return project_id, prd_content, generated_at


class TestPRDEndpointBasics:
    """Test basic PRD endpoint functionality."""

    def test_prd_endpoint_exists(self, api_client, project_with_prd):
        """Test that GET /api/projects/{id}/prd endpoint exists."""
        project_id, _, _ = project_with_prd
        response = api_client.get(f"/api/projects/{project_id}/prd")

        # Should not return 404
        assert response.status_code != 404

    def test_prd_endpoint_returns_json(self, api_client, project_with_prd):
        """Test that PRD endpoint returns JSON response."""
        project_id, _, _ = project_with_prd
        response = api_client.get(f"/api/projects/{project_id}/prd")

        assert response.headers["content-type"] == "application/json"

    def test_prd_endpoint_returns_200_when_available(self, api_client, project_with_prd):
        """Test that PRD endpoint returns 200 when PRD is available."""
        project_id, _, _ = project_with_prd
        response = api_client.get(f"/api/projects/{project_id}/prd")

        assert response.status_code == 200


class TestPRDResponseStructure:
    """Test PRD response structure matches API contract."""

    def test_prd_response_has_required_fields(self, api_client, project_with_prd):
        """Test that PRD response includes all required fields.

        Required fields (API Contract):
        - project_id: string
        - prd_content: string
        - generated_at: ISODate (RFC 3339)
        - updated_at: ISODate (RFC 3339)
        - status: 'available' | 'generating' | 'not_found'
        """
        project_id, _, _ = project_with_prd
        response = api_client.get(f"/api/projects/{project_id}/prd")
        data = response.json()

        # Verify all required fields present
        assert "project_id" in data
        assert "prd_content" in data
        assert "generated_at" in data
        assert "updated_at" in data
        assert "status" in data

    def test_prd_response_project_id_is_string(self, api_client, project_with_prd):
        """Test that project_id is returned as string (not int)."""
        project_id, _, _ = project_with_prd
        response = api_client.get(f"/api/projects/{project_id}/prd")
        data = response.json()

        # project_id should be string
        assert isinstance(data["project_id"], str)
        assert data["project_id"] == str(project_id)

    def test_prd_response_timestamps_are_rfc3339(self, api_client, project_with_prd):
        """Test that timestamps follow RFC 3339 format with timezone."""
        project_id, _, _ = project_with_prd
        response = api_client.get(f"/api/projects/{project_id}/prd")
        data = response.json()

        # Verify generated_at is valid RFC 3339
        generated_at = data["generated_at"]
        assert isinstance(generated_at, str)
        # Should be parseable as ISO format with timezone
        dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        assert dt.tzinfo is not None  # Must have timezone

        # Verify updated_at is valid RFC 3339
        updated_at = data["updated_at"]
        assert isinstance(updated_at, str)
        dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        assert dt.tzinfo is not None

    def test_prd_response_status_is_available(self, api_client, project_with_prd):
        """Test that status is 'available' when PRD exists."""
        project_id, _, _ = project_with_prd
        response = api_client.get(f"/api/projects/{project_id}/prd")
        data = response.json()

        assert data["status"] == "available"

    def test_prd_response_contains_correct_content(self, api_client, project_with_prd):
        """Test that prd_content matches stored content."""
        project_id, prd_content, _ = project_with_prd
        response = api_client.get(f"/api/projects/{project_id}/prd")
        data = response.json()

        assert data["prd_content"] == prd_content


class TestPRDEndpointNotFound:
    """Test PRD endpoint when PRD doesn't exist."""

    def test_prd_not_found_returns_status_not_found(self, api_client):
        """Test that status is 'not_found' when PRD doesn't exist."""
        # Create project without PRD
        project_id = get_app().state.db.create_project(
            name="No PRD Project", description="No PRD Project project"
        )

        response = api_client.get(f"/api/projects/{project_id}/prd")
        data = response.json()

        assert response.status_code == 200
        assert data["status"] == "not_found"

    def test_prd_not_found_returns_empty_content(self, api_client):
        """Test that prd_content is empty when PRD doesn't exist."""
        # Create project without PRD
        project_id = get_app().state.db.create_project(
            name="No PRD Project", description="No PRD Project project"
        )

        response = api_client.get(f"/api/projects/{project_id}/prd")
        data = response.json()

        assert data["prd_content"] == ""

    def test_nonexistent_project_returns_404(self, api_client):
        """Test that nonexistent project returns 404."""
        response = api_client.get("/api/projects/99999/prd")

        assert response.status_code == 404


class TestPRDEndpointEdgeCases:
    """Test PRD endpoint edge cases and error handling."""

    def test_prd_endpoint_handles_invalid_project_id(self, api_client):
        """Test that endpoint handles invalid project ID gracefully."""
        response = api_client.get("/api/projects/invalid/prd")

        # Should return 422 (validation error) or 404
        assert response.status_code in [422, 404]

    def test_prd_endpoint_with_very_large_content(self, api_client):
        """Test that endpoint handles large PRD content."""
        # Create project with large PRD
        project_id = get_app().state.db.create_project(
            name="Large PRD Project", description="Large PRD Project project"
        )

        # Create large PRD content (>100KB)
        large_content = "# PRD\n\n" + ("Lorem ipsum dolor sit amet. " * 10000)
        get_app().state.db.create_memory(
            project_id=project_id, category="prd", key="prd_content", value=large_content
        )

        generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        get_app().state.db.create_memory(
            project_id=project_id, category="prd", key="generated_at", value=generated_at
        )

        response = api_client.get(f"/api/projects/{project_id}/prd")

        assert response.status_code == 200
        data = response.json()
        assert len(data["prd_content"]) > 100000

    def test_prd_updated_at_reflects_latest_change(self, api_client, project_with_prd):
        """Test that updated_at reflects the most recent update."""
        project_id, _, _ = project_with_prd

        # Get initial response
        response1 = api_client.get(f"/api/projects/{project_id}/prd")
        data1 = response1.json()

        # Since we're just reading, updated_at should equal generated_at
        # In a real scenario, updated_at would change on edits
        assert data1["updated_at"] == data1["generated_at"]
