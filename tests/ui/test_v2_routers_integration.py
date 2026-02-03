"""Integration tests for v2 routers (blockers_v2, prd_v2, tasks_v2).

These tests verify that v2 routers:
1. Properly delegate to core modules
2. Handle valid inputs correctly
3. Return appropriate error responses
4. Follow v2 API patterns (workspace-based routing, standard response format)

The tests use FastAPI TestClient with dependency overrides to test the routers
in isolation without requiring a running server.
"""

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Mark all tests in this module as v2
pytestmark = pytest.mark.v2


@pytest.fixture
def test_workspace():
    """Create a temporary workspace for testing.

    Initializes a proper v2 workspace structure with database.
    """
    # Create temporary directory
    temp_dir = Path(tempfile.mkdtemp())
    workspace_path = temp_dir / "test_workspace"
    workspace_path.mkdir(parents=True, exist_ok=True)

    # Initialize workspace using core module
    from codeframe.core.workspace import create_or_load_workspace

    workspace = create_or_load_workspace(workspace_path)

    yield workspace

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_client(test_workspace):
    """Create a FastAPI TestClient with v2 routers and workspace dependency override."""
    from codeframe.ui.routers import blockers_v2, prd_v2, tasks_v2
    from codeframe.ui.dependencies import get_v2_workspace

    # Create a fresh FastAPI app with just the v2 routers
    app = FastAPI()
    app.include_router(blockers_v2.router)
    app.include_router(prd_v2.router)
    app.include_router(tasks_v2.router)

    # Override workspace dependency to return our test workspace
    def get_test_workspace():
        return test_workspace

    app.dependency_overrides[get_v2_workspace] = get_test_workspace

    client = TestClient(app)
    client.workspace = test_workspace  # Attach for test access

    yield client


# ============================================================================
# Blockers v2 Router Tests
# ============================================================================


class TestBlockersV2List:
    """Tests for GET /api/v2/blockers endpoint."""

    def test_list_blockers_empty(self, test_client):
        """List blockers returns empty list when no blockers exist."""
        response = test_client.get("/api/v2/blockers")

        assert response.status_code == 200
        data = response.json()
        assert data["blockers"] == []
        assert data["total"] == 0
        assert "by_status" in data

    def test_list_blockers_with_data(self, test_client):
        """List blockers returns created blockers."""
        # Create a blocker
        create_response = test_client.post(
            "/api/v2/blockers",
            json={"question": "What is the API endpoint?"}
        )
        assert create_response.status_code == 201

        # List blockers
        response = test_client.get("/api/v2/blockers")

        assert response.status_code == 200
        data = response.json()
        assert len(data["blockers"]) == 1
        assert data["total"] == 1
        assert data["blockers"][0]["question"] == "What is the API endpoint?"

    def test_list_blockers_filter_by_status(self, test_client):
        """List blockers can filter by status."""
        # Create a blocker
        test_client.post(
            "/api/v2/blockers",
            json={"question": "Open question"}
        )

        # Filter by OPEN status
        response = test_client.get("/api/v2/blockers?status=OPEN")

        assert response.status_code == 200
        data = response.json()
        assert len(data["blockers"]) == 1

        # Filter by ANSWERED status (should be empty)
        response = test_client.get("/api/v2/blockers?status=ANSWERED")

        assert response.status_code == 200
        data = response.json()
        assert len(data["blockers"]) == 0

    def test_list_blockers_invalid_status(self, test_client):
        """List blockers returns 400 for invalid status."""
        response = test_client.get("/api/v2/blockers?status=INVALID")

        assert response.status_code == 400
        assert "Invalid status" in response.json()["detail"]["error"]


class TestBlockersV2Create:
    """Tests for POST /api/v2/blockers endpoint."""

    def test_create_blocker(self, test_client):
        """Create blocker with valid data."""
        response = test_client.post(
            "/api/v2/blockers",
            json={"question": "What is the database schema?"}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["question"] == "What is the database schema?"
        assert data["status"] == "OPEN"
        assert data["answer"] is None
        assert "id" in data
        assert "created_at" in data

    def test_create_blocker_with_task_id(self, test_client):
        """Create blocker associated with a task."""
        response = test_client.post(
            "/api/v2/blockers",
            json={
                "question": "What authentication should I use?",
                "task_id": "task-123"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["task_id"] == "task-123"

    def test_create_blocker_empty_question(self, test_client):
        """Create blocker with empty question returns 422."""
        response = test_client.post(
            "/api/v2/blockers",
            json={"question": ""}
        )

        # Pydantic validation error returns 422
        assert response.status_code == 422


class TestBlockersV2Get:
    """Tests for GET /api/v2/blockers/{id} endpoint."""

    def test_get_blocker(self, test_client):
        """Get blocker by ID."""
        # Create a blocker
        create_response = test_client.post(
            "/api/v2/blockers",
            json={"question": "Test question"}
        )
        blocker_id = create_response.json()["id"]

        # Get the blocker
        response = test_client.get(f"/api/v2/blockers/{blocker_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == blocker_id
        assert data["question"] == "Test question"

    def test_get_blocker_not_found(self, test_client):
        """Get non-existent blocker returns 404."""
        response = test_client.get("/api/v2/blockers/nonexistent-id")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]["error"].lower()


class TestBlockersV2Answer:
    """Tests for POST /api/v2/blockers/{id}/answer endpoint."""

    def test_answer_blocker(self, test_client):
        """Answer a blocker."""
        # Create a blocker
        create_response = test_client.post(
            "/api/v2/blockers",
            json={"question": "What is the answer?"}
        )
        blocker_id = create_response.json()["id"]

        # Answer the blocker
        response = test_client.post(
            f"/api/v2/blockers/{blocker_id}/answer",
            json={"answer": "The answer is 42."}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ANSWERED"
        assert data["answer"] == "The answer is 42."
        assert data["answered_at"] is not None

    def test_answer_blocker_not_found(self, test_client):
        """Answer non-existent blocker returns 404."""
        response = test_client.post(
            "/api/v2/blockers/nonexistent-id/answer",
            json={"answer": "Some answer"}
        )

        assert response.status_code == 404


class TestBlockersV2Resolve:
    """Tests for POST /api/v2/blockers/{id}/resolve endpoint."""

    def test_resolve_blocker(self, test_client):
        """Resolve an answered blocker."""
        # Create and answer a blocker
        create_response = test_client.post(
            "/api/v2/blockers",
            json={"question": "Question to resolve"}
        )
        blocker_id = create_response.json()["id"]

        test_client.post(
            f"/api/v2/blockers/{blocker_id}/answer",
            json={"answer": "Answer provided"}
        )

        # Resolve the blocker
        response = test_client.post(f"/api/v2/blockers/{blocker_id}/resolve")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "RESOLVED"

    def test_resolve_unanswered_blocker(self, test_client):
        """Resolve unanswered blocker returns 400."""
        # Create a blocker (not answered)
        create_response = test_client.post(
            "/api/v2/blockers",
            json={"question": "Unanswered question"}
        )
        blocker_id = create_response.json()["id"]

        # Try to resolve without answering
        response = test_client.post(f"/api/v2/blockers/{blocker_id}/resolve")

        assert response.status_code == 400
        assert "must be answered" in response.json()["detail"]["detail"].lower()


# ============================================================================
# PRD v2 Router Tests
# ============================================================================


class TestPrdV2List:
    """Tests for GET /api/v2/prd endpoint."""

    def test_list_prds_empty(self, test_client):
        """List PRDs returns empty list when no PRDs exist."""
        response = test_client.get("/api/v2/prd")

        assert response.status_code == 200
        data = response.json()
        assert data["prds"] == []
        assert data["total"] == 0

    def test_list_prds_with_data(self, test_client):
        """List PRDs returns created PRDs."""
        # Create a PRD
        test_client.post(
            "/api/v2/prd",
            json={"content": "# My PRD\n\nThis is the content.", "title": "Test PRD"}
        )

        # List PRDs
        response = test_client.get("/api/v2/prd")

        assert response.status_code == 200
        data = response.json()
        assert len(data["prds"]) == 1
        assert data["total"] == 1
        assert data["prds"][0]["title"] == "Test PRD"


class TestPrdV2Latest:
    """Tests for GET /api/v2/prd/latest endpoint."""

    def test_get_latest_prd_none(self, test_client):
        """Get latest PRD returns 404 when none exist."""
        response = test_client.get("/api/v2/prd/latest")

        assert response.status_code == 404

    def test_get_latest_prd(self, test_client):
        """Get latest PRD returns the most recent PRD."""
        # Create two PRDs
        test_client.post(
            "/api/v2/prd",
            json={"content": "# First PRD\n\nOld content.", "title": "First PRD"}
        )
        test_client.post(
            "/api/v2/prd",
            json={"content": "# Second PRD\n\nNew content.", "title": "Second PRD"}
        )

        # Get latest
        response = test_client.get("/api/v2/prd/latest")

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Second PRD"


class TestPrdV2Create:
    """Tests for POST /api/v2/prd endpoint."""

    def test_create_prd(self, test_client):
        """Create PRD with valid data."""
        response = test_client.post(
            "/api/v2/prd",
            json={
                "content": "# Feature PRD\n\nThis is the feature description.",
                "title": "Feature X"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Feature X"
        assert "Feature PRD" in data["content"]
        assert data["version"] == 1
        assert "id" in data
        assert "created_at" in data

    def test_create_prd_extracts_title(self, test_client):
        """Create PRD extracts title from content if not provided."""
        response = test_client.post(
            "/api/v2/prd",
            json={"content": "# Extracted Title\n\nSome content here."}
        )

        assert response.status_code == 201
        data = response.json()
        # Title should be extracted from markdown header
        assert "Extracted Title" in data["title"]

    def test_create_prd_empty_content(self, test_client):
        """Create PRD with empty content returns 422."""
        response = test_client.post(
            "/api/v2/prd",
            json={"content": ""}
        )

        assert response.status_code == 422


class TestPrdV2Get:
    """Tests for GET /api/v2/prd/{id} endpoint."""

    def test_get_prd(self, test_client):
        """Get PRD by ID."""
        # Create a PRD
        create_response = test_client.post(
            "/api/v2/prd",
            json={"content": "# Test PRD\n\nContent.", "title": "Test"}
        )
        prd_id = create_response.json()["id"]

        # Get the PRD
        response = test_client.get(f"/api/v2/prd/{prd_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == prd_id
        assert data["title"] == "Test"

    def test_get_prd_not_found(self, test_client):
        """Get non-existent PRD returns 404."""
        response = test_client.get("/api/v2/prd/nonexistent-id")

        assert response.status_code == 404


class TestPrdV2Delete:
    """Tests for DELETE /api/v2/prd/{id} endpoint."""

    def test_delete_prd(self, test_client):
        """Delete PRD by ID."""
        # Create a PRD
        create_response = test_client.post(
            "/api/v2/prd",
            json={"content": "# To Delete\n\nContent.", "title": "Delete Me"}
        )
        prd_id = create_response.json()["id"]

        # Delete the PRD
        response = test_client.delete(f"/api/v2/prd/{prd_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify it's gone
        get_response = test_client.get(f"/api/v2/prd/{prd_id}")
        assert get_response.status_code == 404

    def test_delete_prd_not_found(self, test_client):
        """Delete non-existent PRD returns 404."""
        response = test_client.delete("/api/v2/prd/nonexistent-id")

        assert response.status_code == 404


class TestPrdV2Versions:
    """Tests for PRD versioning endpoints."""

    def test_get_prd_versions(self, test_client):
        """Get all versions of a PRD."""
        # Create a PRD
        create_response = test_client.post(
            "/api/v2/prd",
            json={"content": "# V1 Content\n\nOriginal.", "title": "Versioned PRD"}
        )
        prd_id = create_response.json()["id"]

        # Create a new version
        test_client.post(
            f"/api/v2/prd/{prd_id}/versions",
            json={
                "content": "# V2 Content\n\nUpdated.",
                "change_summary": "Updated content for v2"
            }
        )

        # Get versions
        response = test_client.get(f"/api/v2/prd/{prd_id}/versions")

        assert response.status_code == 200
        versions = response.json()
        assert len(versions) == 2
        # Versions should be newest first
        assert versions[0]["version"] == 2
        assert versions[1]["version"] == 1

    def test_create_prd_version(self, test_client):
        """Create a new version of a PRD."""
        # Create initial PRD
        create_response = test_client.post(
            "/api/v2/prd",
            json={"content": "# Original\n\nV1 content.", "title": "Base PRD"}
        )
        prd_id = create_response.json()["id"]

        # Create new version
        response = test_client.post(
            f"/api/v2/prd/{prd_id}/versions",
            json={
                "content": "# Updated\n\nV2 content.",
                "change_summary": "Major update to requirements"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["version"] == 2
        assert data["change_summary"] == "Major update to requirements"
        assert data["parent_id"] == prd_id

    def test_diff_prd_versions(self, test_client):
        """Generate diff between two PRD versions."""
        # Create initial PRD
        create_response = test_client.post(
            "/api/v2/prd",
            json={"content": "# PRD\n\nOriginal content.", "title": "Diff Test"}
        )
        prd_id = create_response.json()["id"]

        # Create new version
        test_client.post(
            f"/api/v2/prd/{prd_id}/versions",
            json={
                "content": "# PRD\n\nModified content.",
                "change_summary": "Changed original to modified"
            }
        )

        # Get diff
        response = test_client.get(f"/api/v2/prd/{prd_id}/diff?v1=1&v2=2")

        assert response.status_code == 200
        data = response.json()
        assert data["version1"] == 1
        assert data["version2"] == 2
        assert "diff" in data
        # Diff should show the change
        assert "-Original" in data["diff"] or "Original" in data["diff"]


# ============================================================================
# Tasks v2 Router Tests
# ============================================================================


@pytest.fixture
def test_client_with_task(test_client):
    """Create a test client with a pre-created task."""
    from codeframe.core import tasks
    from codeframe.core.state_machine import TaskStatus

    # Create a task for testing
    task = tasks.create(
        test_client.workspace,
        title="Test Task",
        description="A task for testing",
        status=TaskStatus.READY,
        priority=1,
    )

    test_client.task = task
    return test_client


class TestTasksV2List:
    """Tests for GET /api/v2/tasks endpoint."""

    def test_list_tasks_empty(self, test_client):
        """List tasks returns empty list when no tasks exist."""
        response = test_client.get("/api/v2/tasks")

        assert response.status_code == 200
        data = response.json()
        assert data["tasks"] == []
        assert data["total"] == 0
        assert "by_status" in data

    def test_list_tasks_with_data(self, test_client_with_task):
        """List tasks returns created tasks."""
        response = test_client_with_task.get("/api/v2/tasks")

        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) >= 1
        assert data["total"] >= 1

    def test_list_tasks_filter_by_status(self, test_client_with_task):
        """List tasks can filter by status."""
        response = test_client_with_task.get("/api/v2/tasks?status=READY")

        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) >= 1
        for task in data["tasks"]:
            assert task["status"] == "READY"

    def test_list_tasks_invalid_status(self, test_client):
        """List tasks returns 400 for invalid status."""
        response = test_client.get("/api/v2/tasks?status=INVALID")

        assert response.status_code == 400


class TestTasksV2Get:
    """Tests for GET /api/v2/tasks/{id} endpoint."""

    def test_get_task(self, test_client_with_task):
        """Get task by ID."""
        task_id = test_client_with_task.task.id

        response = test_client_with_task.get(f"/api/v2/tasks/{task_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == task_id
        assert data["title"] == "Test Task"

    def test_get_task_not_found(self, test_client):
        """Get non-existent task returns 404."""
        response = test_client.get("/api/v2/tasks/nonexistent-id")

        assert response.status_code == 404


class TestTasksV2Update:
    """Tests for PATCH /api/v2/tasks/{id} endpoint."""

    def test_update_task_title(self, test_client_with_task):
        """Update task title."""
        task_id = test_client_with_task.task.id

        response = test_client_with_task.patch(
            f"/api/v2/tasks/{task_id}",
            json={"title": "Updated Title"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"

    def test_update_task_description(self, test_client_with_task):
        """Update task description."""
        task_id = test_client_with_task.task.id

        response = test_client_with_task.patch(
            f"/api/v2/tasks/{task_id}",
            json={"description": "New description"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "New description"

    def test_update_task_priority(self, test_client_with_task):
        """Update task priority."""
        task_id = test_client_with_task.task.id

        response = test_client_with_task.patch(
            f"/api/v2/tasks/{task_id}",
            json={"priority": 5}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["priority"] == 5

    def test_update_task_not_found(self, test_client):
        """Update non-existent task returns 404."""
        response = test_client.patch(
            "/api/v2/tasks/nonexistent-id",
            json={"title": "New Title"}
        )

        assert response.status_code == 404


class TestTasksV2Delete:
    """Tests for DELETE /api/v2/tasks/{id} endpoint."""

    def test_delete_task(self, test_client_with_task):
        """Delete task by ID."""
        task_id = test_client_with_task.task.id

        response = test_client_with_task.delete(f"/api/v2/tasks/{task_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify it's gone
        get_response = test_client_with_task.get(f"/api/v2/tasks/{task_id}")
        assert get_response.status_code == 404

    def test_delete_task_not_found(self, test_client):
        """Delete non-existent task returns 404."""
        response = test_client.delete("/api/v2/tasks/nonexistent-id")

        assert response.status_code == 404


class TestTasksV2Execution:
    """Tests for task execution endpoints."""

    def test_start_task(self, test_client_with_task):
        """Start a task creates a run record."""
        task_id = test_client_with_task.task.id

        response = test_client_with_task.post(f"/api/v2/tasks/{task_id}/start")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["task_id"] == task_id
        assert "run_id" in data

    def test_start_task_not_found(self, test_client):
        """Start non-existent task returns 404."""
        response = test_client.post("/api/v2/tasks/nonexistent-id/start")

        assert response.status_code == 404

    def test_get_task_run(self, test_client_with_task):
        """Get task run status after starting."""
        task_id = test_client_with_task.task.id

        # Start the task
        test_client_with_task.post(f"/api/v2/tasks/{task_id}/start")

        # Get run status
        response = test_client_with_task.get(f"/api/v2/tasks/{task_id}/run")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["task_id"] == task_id
        assert "run_id" in data
        assert "status" in data

    def test_get_task_run_no_run(self, test_client_with_task):
        """Get run for task with no runs returns 404."""
        from codeframe.core import tasks
        from codeframe.core.state_machine import TaskStatus

        # Create a new task that has never been started
        new_task = tasks.create(
            test_client_with_task.workspace,
            title="Never Started Task",
            description="This task was never started",
            status=TaskStatus.READY,
            priority=1,
        )

        response = test_client_with_task.get(f"/api/v2/tasks/{new_task.id}/run")

        assert response.status_code == 404


class TestTasksV2Streaming:
    """Tests for task streaming endpoint."""

    def test_stream_task_no_run(self, test_client_with_task):
        """Stream endpoint returns 404 when no run exists."""
        from codeframe.core import tasks
        from codeframe.core.state_machine import TaskStatus

        # Create a new task that has never been started
        new_task = tasks.create(
            test_client_with_task.workspace,
            title="Never Started Task",
            description="This task was never started",
            status=TaskStatus.READY,
            priority=1,
        )

        response = test_client_with_task.get(f"/api/v2/tasks/{new_task.id}/stream")

        assert response.status_code == 404

    def test_stream_task_not_found(self, test_client):
        """Stream endpoint returns 404 for non-existent task."""
        response = test_client.get("/api/v2/tasks/nonexistent-id/stream")

        assert response.status_code == 404


# ============================================================================
# Error Response Format Tests
# ============================================================================


class TestErrorResponses:
    """Tests that verify v2 routers return standardized error responses."""

    def test_404_error_format(self, test_client):
        """404 errors follow standard format."""
        response = test_client.get("/api/v2/blockers/nonexistent-id")

        assert response.status_code == 404
        detail = response.json()["detail"]
        assert "error" in detail
        assert "code" in detail
        assert "detail" in detail

    def test_400_error_format(self, test_client):
        """400 errors follow standard format."""
        response = test_client.get("/api/v2/blockers?status=INVALID")

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "error" in detail
        assert "code" in detail


# ============================================================================
# Core Module Delegation Tests
# ============================================================================


class TestCoreDelegation:
    """Tests that verify routers properly delegate to core modules."""

    def test_blocker_uses_core_module(self, test_client):
        """Blocker router delegates to core.blockers module."""
        from codeframe.core import blockers

        # Create via API
        response = test_client.post(
            "/api/v2/blockers",
            json={"question": "Core delegation test"}
        )
        blocker_id = response.json()["id"]

        # Verify in core module
        blocker = blockers.get(test_client.workspace, blocker_id)
        assert blocker is not None
        assert blocker.question == "Core delegation test"

    def test_prd_uses_core_module(self, test_client):
        """PRD router delegates to core.prd module."""
        from codeframe.core import prd

        # Create via API
        response = test_client.post(
            "/api/v2/prd",
            json={"content": "# Core Test\n\nContent.", "title": "Core Test"}
        )
        prd_id = response.json()["id"]

        # Verify in core module
        record = prd.get_by_id(test_client.workspace, prd_id)
        assert record is not None
        assert record.title == "Core Test"

    def test_task_uses_core_module(self, test_client):
        """Task router delegates to core.tasks module."""
        from codeframe.core import tasks
        from codeframe.core.state_machine import TaskStatus

        # Create a task via core
        task = tasks.create(
            test_client.workspace,
            title="Core Created Task",
            description="Created via core",
            status=TaskStatus.READY,
            priority=1,
        )

        # Verify via API
        response = test_client.get(f"/api/v2/tasks/{task.id}")
        assert response.status_code == 200
        assert response.json()["title"] == "Core Created Task"


# ============================================================================
# Rate Limiting Integration Tests
# ============================================================================


class TestRateLimitingIntegration:
    """Tests for rate limiting on v2 endpoints."""

    @pytest.fixture(autouse=True)
    def reset_caches(self):
        """Reset rate limit caches before and after each test."""
        from codeframe.config.rate_limits import _reset_rate_limit_config
        from codeframe.core.config import reset_global_config
        from codeframe.lib.rate_limiter import reset_rate_limiter

        _reset_rate_limit_config()
        reset_global_config()
        reset_rate_limiter()
        yield
        _reset_rate_limit_config()
        reset_global_config()
        reset_rate_limiter()

    @pytest.fixture
    def rate_limited_client(self, test_workspace):
        """Create a test client with rate limiting enabled at a low limit."""
        from unittest.mock import patch

        from fastapi import Request
        from slowapi import Limiter
        from slowapi.errors import RateLimitExceeded
        from slowapi.util import get_remote_address

        from codeframe.lib.rate_limiter import rate_limit_exceeded_handler
        from codeframe.ui.dependencies import get_v2_workspace
        from codeframe.ui.routers import blockers_v2

        # Create app with rate limiting
        app = FastAPI()

        # Create limiter with very low limit for testing (3 requests/minute)
        limiter = Limiter(key_func=get_remote_address, default_limits=["3/minute"])
        app.state.limiter = limiter

        # Add rate limit exceeded handler
        app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

        # Create a rate-limited endpoint for testing
        @app.get("/api/v2/test/rate-limited")
        @limiter.limit("3/minute")
        async def rate_limited_endpoint(request: Request):
            return {"status": "ok"}

        # Also include the blockers router for real endpoint testing
        app.include_router(blockers_v2.router)

        # Override workspace dependency
        def get_test_workspace():
            return test_workspace

        app.dependency_overrides[get_v2_workspace] = get_test_workspace

        client = TestClient(app)
        client.workspace = test_workspace

        return client

    def test_rate_limit_allows_requests_within_limit(self, rate_limited_client):
        """Requests within rate limit should succeed."""
        # Make 3 requests (at the limit)
        for i in range(3):
            response = rate_limited_client.get("/api/v2/test/rate-limited")
            assert response.status_code == 200, f"Request {i+1} failed unexpectedly"
            assert response.json()["status"] == "ok"

    def test_rate_limit_exceeded_returns_429(self, rate_limited_client):
        """Exceeding rate limit should return 429 status."""
        # Make requests up to the limit
        for i in range(3):
            response = rate_limited_client.get("/api/v2/test/rate-limited")
            assert response.status_code == 200, f"Request {i+1} should succeed"

        # Next request should be rate limited
        response = rate_limited_client.get("/api/v2/test/rate-limited")
        assert response.status_code == 429

    def test_rate_limit_response_has_retry_after_header(self, rate_limited_client):
        """429 response should include Retry-After header."""
        # Exhaust the limit
        for _ in range(3):
            rate_limited_client.get("/api/v2/test/rate-limited")

        # Get rate limited response
        response = rate_limited_client.get("/api/v2/test/rate-limited")

        assert response.status_code == 429
        assert "Retry-After" in response.headers

    def test_rate_limit_response_body_format(self, rate_limited_client):
        """429 response body should have proper error format."""
        # Exhaust the limit
        for _ in range(3):
            rate_limited_client.get("/api/v2/test/rate-limited")

        # Get rate limited response
        response = rate_limited_client.get("/api/v2/test/rate-limited")

        assert response.status_code == 429
        data = response.json()
        assert data["error"] == "rate_limit_exceeded"
        assert "detail" in data
        assert "retry_after" in data

    def test_rate_limit_on_real_endpoint(self, rate_limited_client):
        """Test rate limiting behavior on actual v2 endpoint.

        Note: This test uses the standard blockers endpoint which in production
        has a 100/minute limit. The test verifies the endpoint is accessible
        and the rate limiting infrastructure is integrated correctly.
        """
        # The blockers endpoint uses rate_limit_standard (100/min in production)
        # With our test client, we're just verifying the infrastructure works
        response = rate_limited_client.get("/api/v2/blockers")

        # Should succeed (within any configured limit)
        assert response.status_code == 200
        data = response.json()
        assert "blockers" in data
        assert "total" in data
