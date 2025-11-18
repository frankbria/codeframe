"""Tests for Issues/Tasks API endpoint (cf-26).

Sprint 2 Foundation Contract:
GET /api/projects/{id}/issues?include=tasks → IssuesResponse

Tests follow RED-GREEN-REFACTOR TDD cycle.
"""

import pytest
from datetime import datetime

from codeframe.core.models import TaskStatus, Issue


def get_app():
    """Get the current app instance after module reload."""
    from codeframe.ui.server import app

    return app


@pytest.fixture(scope="function")
def project_with_issues(api_client):
    """Create test project with issues and tasks.

    Args:
        api_client: FastAPI test client from class-scoped fixture

    Returns:
        Tuple of (project_id, issues, tasks)
    """
    # Create project
    project_id = get_app().state.db.create_project(
        name="Test Issues Project", description="Test Issues Project project"
    )

    # Create issues
    issue1_id = get_app().state.db.create_issue(
        Issue(
            project_id=project_id,
            issue_number="1.1",
            title="Implement authentication",
            description="Add user login and JWT",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            workflow_step=5,
        )
    )

    issue2_id = get_app().state.db.create_issue(
        Issue(
            project_id=project_id,
            issue_number="1.2",
            title="Setup database schema",
            description="Create initial migrations",
            status=TaskStatus.COMPLETED,
            priority=0,
            workflow_step=3,
        )
    )

    # Create tasks for issue 1
    task1_id = get_app().state.db.create_task_with_issue(
        project_id=project_id,
        issue_id=issue1_id,
        task_number="1.1.1",
        parent_issue_number="1.1",
        title="Create User model",
        description="Define User schema",
        status=TaskStatus.COMPLETED,
        priority=0,
        workflow_step=5,
        can_parallelize=False,
        requires_mcp=False,
    )

    task2_id = get_app().state.db.create_task_with_issue(
        project_id=project_id,
        issue_id=issue1_id,
        task_number="1.1.2",
        parent_issue_number="1.1",
        title="Implement JWT generation",
        description="Add JWT token creation",
        status=TaskStatus.IN_PROGRESS,
        priority=0,
        workflow_step=5,
        can_parallelize=False,
        requires_mcp=False,
    )

    return project_id, [issue1_id, issue2_id], [task1_id, task2_id]


class TestIssuesEndpointBasics:
    """Test basic Issues endpoint functionality."""

    def test_issues_endpoint_exists(self, api_client, project_with_issues):
        """Test that GET /api/projects/{id}/issues endpoint exists."""
        project_id, _, _ = project_with_issues
        response = api_client.get(f"/api/projects/{project_id}/issues")

        # Should not return 404
        assert response.status_code != 404

    def test_issues_endpoint_returns_json(self, api_client, project_with_issues):
        """Test that Issues endpoint returns JSON response."""
        project_id, _, _ = project_with_issues
        response = api_client.get(f"/api/projects/{project_id}/issues")

        assert response.headers["content-type"] == "application/json"

    def test_issues_endpoint_returns_200(self, api_client, project_with_issues):
        """Test that Issues endpoint returns 200."""
        project_id, _, _ = project_with_issues
        response = api_client.get(f"/api/projects/{project_id}/issues")

        assert response.status_code == 200


class TestIssuesResponseStructure:
    """Test Issues response structure matches API contract."""

    def test_issues_response_has_required_fields(self, api_client, project_with_issues):
        """Test that Issues response includes all required fields.

        Required fields (API Contract):
        - issues: Issue[]
        - total_issues: number
        - total_tasks: number
        - next_cursor?: string
        - prev_cursor?: string
        """
        project_id, _, _ = project_with_issues
        response = api_client.get(f"/api/projects/{project_id}/issues")
        data = response.json()

        # Verify all required fields present
        assert "issues" in data
        assert "total_issues" in data
        assert "total_tasks" in data

        # Optional cursor fields
        # They may or may not be present depending on pagination

    def test_issues_response_contains_issues_array(self, api_client, project_with_issues):
        """Test that issues field is an array."""
        project_id, _, _ = project_with_issues
        response = api_client.get(f"/api/projects/{project_id}/issues")
        data = response.json()

        assert isinstance(data["issues"], list)
        assert len(data["issues"]) == 2  # We created 2 issues

    def test_issues_response_total_counts(self, api_client, project_with_issues):
        """Test that total counts are correct."""
        project_id, _, _ = project_with_issues
        response = api_client.get(f"/api/projects/{project_id}/issues")
        data = response.json()

        assert data["total_issues"] == 2
        assert data["total_tasks"] == 2  # We created 2 tasks


class TestIssueStructure:
    """Test individual Issue structure matches API contract."""

    def test_issue_has_required_fields(self, api_client, project_with_issues):
        """Test that each Issue has all required fields.

        Required fields (API Contract):
        - id: string
        - issue_number: string
        - title: string
        - description: string
        - status: WorkStatus
        - priority: number
        - depends_on: string[]
        - proposed_by: 'agent' | 'human'
        - created_at: ISODate
        - updated_at: ISODate
        - completed_at: ISODate | null
        """
        project_id, _, _ = project_with_issues
        response = api_client.get(f"/api/projects/{project_id}/issues")
        data = response.json()

        issue = data["issues"][0]

        # Verify all required fields
        assert "id" in issue
        assert "issue_number" in issue
        assert "title" in issue
        assert "description" in issue
        assert "status" in issue
        assert "priority" in issue
        assert "depends_on" in issue
        assert "proposed_by" in issue
        assert "created_at" in issue
        assert "updated_at" in issue
        assert "completed_at" in issue

    def test_issue_id_is_string(self, api_client, project_with_issues):
        """Test that issue id is returned as string (not int)."""
        project_id, _, _ = project_with_issues
        response = api_client.get(f"/api/projects/{project_id}/issues")
        data = response.json()

        issue = data["issues"][0]
        assert isinstance(issue["id"], str)

    def test_issue_depends_on_is_array(self, api_client, project_with_issues):
        """Test that depends_on is an array."""
        project_id, _, _ = project_with_issues
        response = api_client.get(f"/api/projects/{project_id}/issues")
        data = response.json()

        issue = data["issues"][0]
        assert isinstance(issue["depends_on"], list)

    def test_issue_proposed_by_is_valid(self, api_client, project_with_issues):
        """Test that proposed_by is either 'agent' or 'human'."""
        project_id, _, _ = project_with_issues
        response = api_client.get(f"/api/projects/{project_id}/issues")
        data = response.json()

        issue = data["issues"][0]
        assert issue["proposed_by"] in ["agent", "human"]

    def test_issue_timestamps_are_rfc3339(self, api_client, project_with_issues):
        """Test that timestamps follow RFC 3339 format with timezone."""
        project_id, _, _ = project_with_issues
        response = api_client.get(f"/api/projects/{project_id}/issues")
        data = response.json()

        issue = data["issues"][0]

        # Verify created_at is valid RFC 3339
        created_at = issue["created_at"]
        assert isinstance(created_at, str)
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        assert dt.tzinfo is not None

        # Verify updated_at is valid RFC 3339
        updated_at = issue["updated_at"]
        assert isinstance(updated_at, str)
        dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        assert dt.tzinfo is not None


class TestIssuesWithTasks:
    """Test Issues endpoint with ?include=tasks query param."""

    def test_issues_include_tasks_query_param(self, api_client, project_with_issues):
        """Test that ?include=tasks query param includes tasks in response."""
        project_id, _, _ = project_with_issues
        response = api_client.get(f"/api/projects/{project_id}/issues?include=tasks")
        data = response.json()

        # First issue should have tasks
        issue = data["issues"][0]
        assert "tasks" in issue

    def test_issue_tasks_is_array(self, api_client, project_with_issues):
        """Test that tasks field is an array when included."""
        project_id, _, _ = project_with_issues
        response = api_client.get(f"/api/projects/{project_id}/issues?include=tasks")
        data = response.json()

        issue = data["issues"][0]
        assert isinstance(issue["tasks"], list)

    def test_issue_tasks_count(self, api_client, project_with_issues):
        """Test that first issue has correct number of tasks."""
        project_id, _, _ = project_with_issues
        response = api_client.get(f"/api/projects/{project_id}/issues?include=tasks")
        data = response.json()

        # First issue should have 2 tasks
        issue = data["issues"][0]
        assert len(issue["tasks"]) == 2


class TestTaskStructure:
    """Test individual Task structure matches API contract."""

    def test_task_has_required_fields(self, api_client, project_with_issues):
        """Test that each Task has all required fields.

        Required fields (API Contract):
        - id: string
        - task_number: string
        - title: string
        - description: string
        - status: WorkStatus
        - depends_on: string[]
        - proposed_by: 'agent' | 'human'
        - created_at: ISODate
        - updated_at: ISODate
        - completed_at: ISODate | null
        """
        project_id, _, _ = project_with_issues
        response = api_client.get(f"/api/projects/{project_id}/issues?include=tasks")
        data = response.json()

        task = data["issues"][0]["tasks"][0]

        # Verify all required fields
        assert "id" in task
        assert "task_number" in task
        assert "title" in task
        assert "description" in task
        assert "status" in task
        assert "depends_on" in task
        assert "proposed_by" in task
        assert "created_at" in task
        assert "updated_at" in task
        assert "completed_at" in task

    def test_task_id_is_string(self, api_client, project_with_issues):
        """Test that task id is returned as string (not int)."""
        project_id, _, _ = project_with_issues
        response = api_client.get(f"/api/projects/{project_id}/issues?include=tasks")
        data = response.json()

        task = data["issues"][0]["tasks"][0]
        assert isinstance(task["id"], str)

    def test_task_depends_on_is_array(self, api_client, project_with_issues):
        """Test that task depends_on is an array."""
        project_id, _, _ = project_with_issues
        response = api_client.get(f"/api/projects/{project_id}/issues?include=tasks")
        data = response.json()

        task = data["issues"][0]["tasks"][0]
        assert isinstance(task["depends_on"], list)


class TestIssuesEndpointEdgeCases:
    """Test Issues endpoint edge cases and error handling."""

    def test_issues_without_tasks_query_param(self, api_client, project_with_issues):
        """Test that tasks field is not included without ?include=tasks."""
        project_id, _, _ = project_with_issues
        response = api_client.get(f"/api/projects/{project_id}/issues")
        data = response.json()

        # Tasks should not be included
        issue = data["issues"][0]
        assert "tasks" not in issue

    def test_empty_issues_list(self, api_client):
        """Test that empty project returns empty issues array."""
        # Create project without issues
        project_id = get_app().state.db.create_project(
            name="Empty Project", description="Empty Project project"
        )

        response = api_client.get(f"/api/projects/{project_id}/issues")
        data = response.json()

        assert data["issues"] == []
        assert data["total_issues"] == 0
        assert data["total_tasks"] == 0

    def test_nonexistent_project_returns_404(self, api_client):
        """Test that nonexistent project returns 404."""
        response = api_client.get("/api/projects/99999/issues")

        assert response.status_code == 404

    def test_issues_endpoint_handles_invalid_project_id(self, api_client):
        """Test that endpoint handles invalid project ID gracefully."""
        response = api_client.get("/api/projects/invalid/issues")

        # Should return 422 (validation error) or 404
        assert response.status_code in [422, 404]
