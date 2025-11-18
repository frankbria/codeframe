"""Tests for Review API endpoints (Sprint 9 - User Story 1)

TDD approach: Write tests first, ensure they fail, then implement.
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile

from codeframe.ui.server import app
from codeframe.persistence.database import Database
from codeframe.core.models import Task, TaskStatus


@pytest.fixture
def db():
    """Create a test database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    db = Database(db_path)
    db.initialize()
    yield db

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def client(db):
    """Create a test client with database."""
    app.state.db = db

    # Clear review cache before each test
    from codeframe.ui import server

    server.review_cache.clear()

    return TestClient(app)


@pytest.fixture
def project_id(db):
    """Create a test project."""
    project_id = db.create_project(
        name="Test Project",
        description="Project for review API testing",
        project_path="/tmp/test_project",
    )
    return project_id


@pytest.fixture
def task_id(db, project_id):
    """Create a test task."""
    task = Task(
        project_id=project_id,
        title="Test task for review",
        description="Task to test review functionality",
        status=TaskStatus.IN_PROGRESS,
        priority=1,
        workflow_step=10,  # Testing phase
    )
    task_id = db.create_task(task)
    return task_id


@pytest.fixture
def bad_code_file():
    """Create a temporary file with code quality issues."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(
            """
# Bad code with multiple quality issues
PASSWORD = "admin123"  # Hardcoded password
API_KEY = "secret_key_123"  # Hardcoded secret

def complex_processor(data):
    # High cyclomatic complexity
    if data:
        if isinstance(data, dict):
            if "user" in data:
                if data["user"]:
                    if "id" in data["user"]:
                        if data["user"]["id"]:
                            return data["user"]["id"]
    return None

def sql_injection_risk(user_input):
    # SQL injection vulnerability
    query = f"SELECT * FROM users WHERE name = '{user_input}'"
    return query

def command_injection_risk(filename):
    # Command injection vulnerability
    import subprocess
    subprocess.run(f"cat {filename}", shell=True)
"""
        )
        file_path = Path(f.name)

    yield file_path

    # Cleanup
    file_path.unlink(missing_ok=True)


@pytest.fixture
def good_code_file():
    """Create a temporary file with good quality code."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(
            '''
"""Example module with good code quality."""

from typing import Optional, List


def process_data(data: Optional[List[dict]]) -> List[str]:
    """Process input data and return results.

    Args:
        data: List of dictionaries to process

    Returns:
        List of processed values
    """
    if not data:
        return []

    results = []
    for item in data:
        if item.get("valid"):
            value = item.get("value")
            if value is not None:
                results.append(str(value))

    return results


def validate_input(value: any) -> bool:
    """Validate input value.

    Args:
        value: Value to validate

    Returns:
        True if valid, False otherwise
    """
    if value is None:
        return False
    if not isinstance(value, (int, str, float)):
        return False
    return True
'''
        )
        file_path = Path(f.name)

    yield file_path

    # Cleanup
    file_path.unlink(missing_ok=True)


class TestReviewAPI:
    """Test Review API endpoints."""

    def test_post_review_endpoint_exists(self, client, project_id, task_id, bad_code_file):
        """T056: POST /api/agents/{agent_id}/review endpoint exists and returns valid response.

        RED PHASE: This test should FAIL because the endpoint doesn't exist yet.
        """
        # Arrange
        agent_id = "review-001"
        review_request = {
            "task_id": task_id,
            "project_id": project_id,
            "files_modified": [str(bad_code_file)],
        }

        # Act
        response = client.post(f"/api/agents/{agent_id}/review", json=review_request)

        # Assert
        assert (
            response.status_code == 200
        ), f"Expected 200, got {response.status_code}. Response: {response.text}"

        data = response.json()
        assert "status" in data
        assert "overall_score" in data
        assert "findings" in data
        assert isinstance(data["findings"], list)

    def test_post_review_endpoint_validates_request(self, client):
        """T056: POST /api/agents/{agent_id}/review validates request body.

        RED PHASE: This test should FAIL because the endpoint doesn't exist yet.
        """
        # Arrange
        agent_id = "review-001"
        invalid_request = {}  # Missing required fields

        # Act
        response = client.post(f"/api/agents/{agent_id}/review", json=invalid_request)

        # Assert
        assert response.status_code in [
            400,
            422,
        ], f"Expected validation error (400 or 422), got {response.status_code}"

    def test_post_review_endpoint_runs_quality_checks(
        self, client, project_id, task_id, bad_code_file
    ):
        """T056: POST /api/agents/{agent_id}/review runs all quality checks.

        RED PHASE: This test should FAIL because the endpoint doesn't exist yet.
        """
        # Arrange
        agent_id = "review-001"
        review_request = {
            "task_id": task_id,
            "project_id": project_id,
            "files_modified": [str(bad_code_file)],
        }

        # Act
        response = client.post(f"/api/agents/{agent_id}/review", json=review_request)

        # Assert
        assert response.status_code == 200

        data = response.json()

        # Should detect complexity issues
        assert any(
            f.get("category") == "complexity" for f in data.get("findings", [])
        ), "Should detect complexity issues"

        # Should detect security issues
        assert any(
            f.get("category") == "security" for f in data.get("findings", [])
        ), "Should detect security issues"

        # Overall score should reflect poor code quality
        assert (
            data["overall_score"] < 70
        ), f"Expected poor score for bad code, got {data['overall_score']}"

    def test_post_review_endpoint_creates_blocker_on_failure(
        self, client, db, project_id, task_id, bad_code_file
    ):
        """T056: POST /api/agents/{agent_id}/review creates blocker when review fails.

        RED PHASE: This test should FAIL because the endpoint doesn't exist yet.
        """
        # Arrange
        agent_id = "review-001"
        review_request = {
            "task_id": task_id,
            "project_id": project_id,
            "files_modified": [str(bad_code_file)],
        }

        # Act
        response = client.post(f"/api/agents/{agent_id}/review", json=review_request)

        # Assert
        assert response.status_code == 200

        data = response.json()

        # If review rejected, should create blocker
        if data.get("status") in ["rejected", "changes_requested"]:
            result = db.list_blockers(project_id=project_id)
            blockers = result.get("blockers", [])
            task_blockers = [b for b in blockers if b["task_id"] == task_id]

            assert len(task_blockers) > 0, "Should create blocker on review failure"

            # Blocker should contain review findings
            blocker = task_blockers[0]
            assert (
                "review" in blocker["question"].lower()
                or "code review" in blocker["question"].lower()
            )

    def test_get_review_status_endpoint_exists(self, client, project_id, task_id, bad_code_file):
        """T057: GET /api/tasks/{task_id}/review-status endpoint exists.

        RED PHASE: This test should FAIL because the endpoint doesn't exist yet.
        """
        # Arrange: First trigger a review
        agent_id = "review-001"
        review_request = {
            "task_id": task_id,
            "project_id": project_id,
            "files_modified": [str(bad_code_file)],
        }
        client.post(f"/api/agents/{agent_id}/review", json=review_request)

        # Act: Get review status
        response = client.get(f"/api/tasks/{task_id}/review-status")

        # Assert
        assert (
            response.status_code == 200
        ), f"Expected 200, got {response.status_code}. Response: {response.text}"

        data = response.json()
        assert "has_review" in data
        assert "status" in data
        assert "overall_score" in data
        assert "findings_count" in data

    def test_get_review_status_no_review_yet(self, client, task_id):
        """T057: GET /api/tasks/{task_id}/review-status returns empty when no review exists.

        RED PHASE: This test should FAIL because the endpoint doesn't exist yet.
        """
        # Act: Get review status for task with no review
        response = client.get(f"/api/tasks/{task_id}/review-status")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert not data["has_review"]
        assert data["status"] is None
        assert data["overall_score"] is None

    def test_get_review_stats_endpoint_exists(self, client, project_id, task_id, bad_code_file):
        """T058: GET /api/projects/{project_id}/review-stats endpoint exists.

        RED PHASE: This test should FAIL because the endpoint doesn't exist yet.
        """
        # Arrange: Trigger a couple of reviews
        agent_id = "review-001"

        # First review
        review_request = {
            "task_id": task_id,
            "project_id": project_id,
            "files_modified": [str(bad_code_file)],
        }
        client.post(f"/api/agents/{agent_id}/review", json=review_request)

        # Act: Get review stats
        response = client.get(f"/api/projects/{project_id}/review-stats")

        # Assert
        assert (
            response.status_code == 200
        ), f"Expected 200, got {response.status_code}. Response: {response.text}"

        data = response.json()
        assert "total_reviews" in data
        assert "approved_count" in data
        assert "changes_requested_count" in data
        assert "rejected_count" in data
        assert "average_score" in data

    def test_get_review_stats_aggregates_correctly(
        self, client, db, project_id, good_code_file, bad_code_file
    ):
        """T058: GET /api/projects/{project_id}/review-stats aggregates multiple reviews.

        RED PHASE: This test should FAIL because the endpoint doesn't exist yet.
        """
        # Arrange: Create two tasks
        from codeframe.core.models import Task, TaskStatus

        task1 = Task(
            project_id=project_id,
            title="Task 1",
            description="Good code task",
            status=TaskStatus.IN_PROGRESS,
            priority=1,
            workflow_step=10,
        )
        task1_id = db.create_task(task1)

        task2 = Task(
            project_id=project_id,
            title="Task 2",
            description="Bad code task",
            status=TaskStatus.IN_PROGRESS,
            priority=1,
            workflow_step=10,
        )
        task2_id = db.create_task(task2)

        # Review task 1 with good code (should approve)
        agent_id = "review-001"
        review_request1 = {
            "task_id": task1_id,
            "project_id": project_id,
            "files_modified": [str(good_code_file)],
        }
        response1 = client.post(f"/api/agents/{agent_id}/review", json=review_request1)
        review1_data = response1.json()

        # Review task 2 with bad code (should request changes or reject)
        review_request2 = {
            "task_id": task2_id,
            "project_id": project_id,
            "files_modified": [str(bad_code_file)],
        }
        response2 = client.post(f"/api/agents/{agent_id}/review", json=review_request2)
        review2_data = response2.json()

        # Act: Get review stats
        response = client.get(f"/api/projects/{project_id}/review-stats")

        # Assert
        assert response.status_code == 200
        data = response.json()

        # Should have 2 total reviews
        assert data["total_reviews"] == 2

        # Should correctly categorize reviews
        if review1_data["status"] == "approved":
            assert data["approved_count"] >= 1
        if review2_data["status"] in ["changes_requested", "rejected"]:
            assert data["changes_requested_count"] + data["rejected_count"] >= 1

        # Average score should be between the two review scores
        avg_score = (review1_data["overall_score"] + review2_data["overall_score"]) / 2
        assert data["average_score"] == pytest.approx(avg_score, rel=0.1)

    def test_get_review_stats_no_reviews_yet(self, client, project_id):
        """T058: GET /api/projects/{project_id}/review-stats returns zeros when no reviews exist.

        RED PHASE: This test should FAIL because the endpoint doesn't exist yet.
        """
        # Act: Get review stats for project with no reviews
        response = client.get(f"/api/projects/{project_id}/review-stats")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_reviews"] == 0
        assert data["approved_count"] == 0
        assert data["changes_requested_count"] == 0
        assert data["rejected_count"] == 0
        assert data["average_score"] == 0.0
