"""Tests for Blocker Resolution API endpoint (049-human-in-loop).

Phase 4 / User Story 2: Blocker Resolution via Dashboard
POST /api/blockers/{blocker_id}/resolve → BlockerResolveResponse

Tests follow RED-GREEN-REFACTOR TDD cycle.
"""

import pytest
from datetime import datetime

from codeframe.core.models import BlockerType, BlockerStatus


def get_app():
    """Get the current app instance after module reload.

    Imports app locally to ensure we get the freshly reloaded instance
    after api_client fixture reloads codeframe.ui.server.
    """
    from codeframe.ui.server import app

    return app


@pytest.fixture(scope="function")
def project_with_blocker(api_client):
    """Create test project with a pending blocker.

    Args:
        api_client: FastAPI test client

    Returns:
        Tuple of (project_id, blocker_id, agent_id, question)
    """
    # Create project
    project_id = get_app().state.db.create_project(
        name="Test Blocker Project", description="Test project for blocker resolution API tests"
    )

    # Create a blocker
    agent_id = "backend-worker-001"
    question = "Should I use JWT or session-based authentication?"
    blocker_id = get_app().state.db.create_blocker(
        agent_id=agent_id,
        project_id=project_id,
        task_id=None,
        blocker_type=BlockerType.SYNC,
        question=question,
    )

    return project_id, blocker_id, agent_id, question


class TestBlockerResolveEndpointBasics:
    """Test basic blocker resolution endpoint functionality."""

    def test_resolve_endpoint_exists(self, api_client, project_with_blocker):
        """Test that POST /api/blockers/{id}/resolve endpoint exists."""
        _, blocker_id, _, _ = project_with_blocker
        response = api_client.post(
            f"/api/blockers/{blocker_id}/resolve",
            json={"answer": "Use JWT for stateless API authentication"},
        )

        # Should not return 404
        assert response.status_code != 404

    def test_resolve_endpoint_returns_json(self, api_client, project_with_blocker):
        """Test that resolve endpoint returns JSON response."""
        _, blocker_id, _, _ = project_with_blocker
        response = api_client.post(
            f"/api/blockers/{blocker_id}/resolve",
            json={"answer": "Use JWT for stateless API authentication"},
        )

        assert response.headers["content-type"] == "application/json"

    def test_resolve_endpoint_returns_200_on_success(self, api_client, project_with_blocker):
        """Test that resolve endpoint returns 200 on successful resolution."""
        _, blocker_id, _, _ = project_with_blocker
        response = api_client.post(
            f"/api/blockers/{blocker_id}/resolve",
            json={"answer": "Use JWT for stateless API authentication"},
        )

        assert response.status_code == 200


class TestBlockerResolveResponseStructure:
    """Test blocker resolution response structure matches API contract."""

    def test_resolve_response_has_required_fields(self, api_client, project_with_blocker):
        """Test that resolve response includes all required fields.

        Required fields (API Contract):
        - blocker_id: int
        - status: 'RESOLVED'
        - resolved_at: ISODate (RFC 3339)
        """
        _, blocker_id, _, _ = project_with_blocker
        response = api_client.post(
            f"/api/blockers/{blocker_id}/resolve", json={"answer": "Use JWT"}
        )
        data = response.json()

        # Verify all required fields present
        assert "blocker_id" in data
        assert "status" in data
        assert "resolved_at" in data

    def test_resolve_response_blocker_id_is_int(self, api_client, project_with_blocker):
        """Test that blocker_id is returned as int."""
        _, blocker_id, _, _ = project_with_blocker
        response = api_client.post(
            f"/api/blockers/{blocker_id}/resolve", json={"answer": "Use JWT"}
        )
        data = response.json()

        assert isinstance(data["blocker_id"], int)
        assert data["blocker_id"] == blocker_id

    def test_resolve_response_status_is_resolved(self, api_client, project_with_blocker):
        """Test that status is 'RESOLVED' after successful resolution."""
        _, blocker_id, _, _ = project_with_blocker
        response = api_client.post(
            f"/api/blockers/{blocker_id}/resolve", json={"answer": "Use JWT"}
        )
        data = response.json()

        assert data["status"] == "RESOLVED"

    def test_resolve_response_timestamp_is_rfc3339(self, api_client, project_with_blocker):
        """Test that resolved_at follows RFC 3339 format with timezone."""
        _, blocker_id, _, _ = project_with_blocker
        response = api_client.post(
            f"/api/blockers/{blocker_id}/resolve", json={"answer": "Use JWT"}
        )
        data = response.json()

        # Verify resolved_at is valid RFC 3339
        resolved_at = data["resolved_at"]
        assert isinstance(resolved_at, str)
        # Should be parseable as ISO format with timezone
        dt = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
        assert dt.tzinfo is not None  # Must have timezone


class TestBlockerResolutionPersistence:
    """Test that blocker resolution is persisted to database."""

    def test_blocker_status_updated_in_database(self, api_client, project_with_blocker):
        """Test that blocker status is updated to RESOLVED in database."""
        _, blocker_id, _, _ = project_with_blocker

        # Verify initial status is PENDING
        blocker_before = get_app().state.db.get_blocker(blocker_id)
        assert blocker_before["status"] == BlockerStatus.PENDING.value

        # Resolve blocker
        api_client.post(f"/api/blockers/{blocker_id}/resolve", json={"answer": "Use JWT"})

        # Verify status updated to RESOLVED
        blocker_after = get_app().state.db.get_blocker(blocker_id)
        assert blocker_after["status"] == BlockerStatus.RESOLVED.value

    def test_answer_stored_in_database(self, api_client, project_with_blocker):
        """Test that user's answer is stored in database."""
        _, blocker_id, _, _ = project_with_blocker

        answer = "Use JWT for stateless API authentication"
        api_client.post(f"/api/blockers/{blocker_id}/resolve", json={"answer": answer})

        # Verify answer stored
        blocker = get_app().state.db.get_blocker(blocker_id)
        assert blocker["answer"] == answer

    def test_resolved_at_timestamp_stored(self, api_client, project_with_blocker):
        """Test that resolved_at timestamp is stored in database."""
        _, blocker_id, _, _ = project_with_blocker

        # Verify no resolved_at before resolution
        blocker_before = get_app().state.db.get_blocker(blocker_id)
        assert blocker_before["resolved_at"] is None

        # Resolve blocker
        api_client.post(f"/api/blockers/{blocker_id}/resolve", json={"answer": "Use JWT"})

        # Verify resolved_at is now set
        blocker_after = get_app().state.db.get_blocker(blocker_id)
        assert blocker_after["resolved_at"] is not None


class TestBlockerResolutionValidation:
    """Test input validation for blocker resolution."""

    def test_resolve_requires_answer_field(self, api_client, project_with_blocker):
        """Test that answer field is required."""
        _, blocker_id, _, _ = project_with_blocker
        response = api_client.post(f"/api/blockers/{blocker_id}/resolve", json={})

        # Should return 422 (validation error)
        assert response.status_code == 422

    def test_resolve_rejects_empty_answer(self, api_client, project_with_blocker):
        """Test that empty answer is rejected."""
        _, blocker_id, _, _ = project_with_blocker
        response = api_client.post(f"/api/blockers/{blocker_id}/resolve", json={"answer": ""})

        # Should return 422 (validation error)
        assert response.status_code == 422

    def test_resolve_rejects_whitespace_only_answer(self, api_client, project_with_blocker):
        """Test that whitespace-only answer is rejected."""
        _, blocker_id, _, _ = project_with_blocker
        response = api_client.post(
            f"/api/blockers/{blocker_id}/resolve", json={"answer": "   \n\t  "}
        )

        # Should return 422 (validation error)
        assert response.status_code == 422

    def test_resolve_rejects_answer_exceeding_max_length(self, api_client, project_with_blocker):
        """Test that answer exceeding 5000 characters is rejected."""
        _, blocker_id, _, _ = project_with_blocker

        # Create answer with 5001 characters
        long_answer = "A" * 5001

        response = api_client.post(
            f"/api/blockers/{blocker_id}/resolve", json={"answer": long_answer}
        )

        # Should return 422 (validation error)
        assert response.status_code == 422

    def test_resolve_accepts_answer_at_max_length(self, api_client, project_with_blocker):
        """Test that answer with exactly 5000 characters is accepted."""
        _, blocker_id, _, _ = project_with_blocker

        # Create answer with exactly 5000 characters
        max_answer = "A" * 5000

        response = api_client.post(
            f"/api/blockers/{blocker_id}/resolve", json={"answer": max_answer}
        )

        # Should succeed
        assert response.status_code == 200


class TestBlockerResolutionConflicts:
    """Test duplicate resolution prevention (409 Conflict)."""

    def test_duplicate_resolution_returns_409(self, api_client, project_with_blocker):
        """Test that resolving already-resolved blocker returns 409 Conflict."""
        _, blocker_id, _, _ = project_with_blocker

        # First resolution - should succeed
        response1 = api_client.post(
            f"/api/blockers/{blocker_id}/resolve", json={"answer": "Answer 1"}
        )
        assert response1.status_code == 200

        # Second resolution - should fail with 409
        response2 = api_client.post(
            f"/api/blockers/{blocker_id}/resolve", json={"answer": "Answer 2"}
        )
        assert response2.status_code == 409

    def test_duplicate_resolution_preserves_first_answer(self, api_client, project_with_blocker):
        """Test that duplicate resolution doesn't overwrite first answer."""
        _, blocker_id, _, _ = project_with_blocker

        # First resolution
        api_client.post(f"/api/blockers/{blocker_id}/resolve", json={"answer": "Answer 1"})

        # Second resolution (should fail)
        api_client.post(f"/api/blockers/{blocker_id}/resolve", json={"answer": "Answer 2"})

        # Verify first answer preserved
        blocker = get_app().state.db.get_blocker(blocker_id)
        assert blocker["answer"] == "Answer 1"

    def test_conflict_response_includes_blocker_id(self, api_client, project_with_blocker):
        """Test that 409 conflict response includes blocker_id."""
        _, blocker_id, _, _ = project_with_blocker

        # First resolution
        api_client.post(f"/api/blockers/{blocker_id}/resolve", json={"answer": "Answer 1"})

        # Second resolution
        response = api_client.post(
            f"/api/blockers/{blocker_id}/resolve", json={"answer": "Answer 2"}
        )
        data = response.json()

        assert "blocker_id" in data
        assert data["blocker_id"] == blocker_id

    def test_conflict_response_includes_error_message(self, api_client, project_with_blocker):
        """Test that 409 conflict response includes helpful error message."""
        _, blocker_id, _, _ = project_with_blocker

        # First resolution
        api_client.post(f"/api/blockers/{blocker_id}/resolve", json={"answer": "Answer 1"})

        # Second resolution
        response = api_client.post(
            f"/api/blockers/{blocker_id}/resolve", json={"answer": "Answer 2"}
        )
        data = response.json()

        assert "error" in data
        assert "already resolved" in data["error"].lower()


class TestBlockerResolutionNotFound:
    """Test blocker resolution for non-existent blockers."""

    def test_nonexistent_blocker_returns_404(self, api_client):
        """Test that resolving non-existent blocker returns 404."""
        response = api_client.post("/api/blockers/99999/resolve", json={"answer": "Some answer"})

        assert response.status_code == 404

    def test_404_response_includes_blocker_id(self, api_client):
        """Test that 404 response includes blocker_id."""
        response = api_client.post("/api/blockers/99999/resolve", json={"answer": "Some answer"})
        data = response.json()

        assert "blocker_id" in data or "detail" in data

    def test_invalid_blocker_id_returns_422(self, api_client):
        """Test that invalid blocker ID format returns 422."""
        response = api_client.post("/api/blockers/invalid/resolve", json={"answer": "Some answer"})

        # Should return 422 (validation error)
        assert response.status_code == 422
