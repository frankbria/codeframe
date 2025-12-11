"""Tests for Project-Level Code Reviews API endpoint.

Tests for GET /api/projects/{project_id}/code-reviews endpoint
which aggregates code review findings across all tasks in a project.
"""

import pytest
from codeframe.core.models import CodeReview, Severity, ReviewCategory, Task, TaskStatus


def get_app():
    """Get the current app instance after module reload."""
    from codeframe.ui.server import app
    return app


@pytest.fixture(scope="function")
def project_with_reviews(api_client):
    """Create test project with tasks and code review findings.

    Args:
        api_client: FastAPI test client from class-scoped fixture

    Returns:
        Tuple of (project_id, task_ids, review_ids)
    """
    # Create project
    project_id = get_app().state.db.create_project(
        name="Test Review Project",
        description="Test project for code reviews API"
    )

    # Create tasks
    task1 = Task(
        project_id=project_id,
        title="Implement user authentication",
        description="Add JWT-based authentication",
        status=TaskStatus.IN_PROGRESS
    )
    task1_id = get_app().state.db.create_task(task1)

    task2 = Task(
        project_id=project_id,
        title="Add API rate limiting",
        description="Implement rate limiting middleware",
        status=TaskStatus.IN_PROGRESS
    )
    task2_id = get_app().state.db.create_task(task2)

    # Create code review findings for task 1
    review1 = CodeReview(
        task_id=task1_id,
        agent_id="review-001",
        project_id=project_id,
        file_path="codeframe/api/auth.py",
        line_number=45,
        severity=Severity.CRITICAL,
        category=ReviewCategory.SECURITY,
        message="SQL injection vulnerability in login query",
        recommendation="Use parameterized queries or ORM",
        code_snippet='cursor.execute(f"SELECT * FROM users WHERE username={username}")'
    )

    review2 = CodeReview(
        task_id=task1_id,
        agent_id="review-001",
        project_id=project_id,
        file_path="codeframe/api/auth.py",
        line_number=67,
        severity=Severity.HIGH,
        category=ReviewCategory.SECURITY,
        message="Password stored in plaintext",
        recommendation="Use bcrypt or argon2 for password hashing",
        code_snippet='db.save_user(username, password)'
    )

    review3 = CodeReview(
        task_id=task1_id,
        agent_id="review-001",
        project_id=project_id,
        file_path="codeframe/api/auth.py",
        line_number=89,
        severity=Severity.MEDIUM,
        category=ReviewCategory.QUALITY,
        message="Missing input validation for username",
        recommendation="Add length and character validation",
        code_snippet='username = request.json["username"]'
    )

    # Create code review findings for task 2
    review4 = CodeReview(
        task_id=task2_id,
        agent_id="review-001",
        project_id=project_id,
        file_path="codeframe/api/middleware.py",
        line_number=23,
        severity=Severity.MEDIUM,
        category=ReviewCategory.PERFORMANCE,
        message="Rate limiter uses in-memory storage",
        recommendation="Consider using Redis for distributed rate limiting",
        code_snippet='rate_limits = {}'
    )

    review5 = CodeReview(
        task_id=task2_id,
        agent_id="review-001",
        project_id=project_id,
        file_path="codeframe/api/middleware.py",
        line_number=45,
        severity=Severity.LOW,
        category=ReviewCategory.MAINTAINABILITY,
        message="Magic number for rate limit threshold",
        recommendation="Extract to configuration constant",
        code_snippet='if count > 100:'
    )

    review6 = CodeReview(
        task_id=task2_id,
        agent_id="review-001",
        project_id=project_id,
        file_path="codeframe/api/middleware.py",
        line_number=56,
        severity=Severity.INFO,
        category=ReviewCategory.STYLE,
        message="Line exceeds 88 characters",
        recommendation="Break into multiple lines",
        code_snippet='response = JSONResponse(status_code=429, content={"error": "Rate limit exceeded"})'
    )

    # Save all reviews
    review_ids = []
    for review in [review1, review2, review3, review4, review5, review6]:
        review_id = get_app().state.db.save_code_review(review)
        review_ids.append(review_id)

    return project_id, [task1_id, task2_id], review_ids


@pytest.fixture(scope="function")
def empty_project(api_client):
    """Create test project with no code reviews.

    Args:
        api_client: FastAPI test client from class-scoped fixture

    Returns:
        project_id
    """
    project_id = get_app().state.db.create_project(
        name="Empty Project",
        description="Project with no code reviews"
    )
    return project_id


class TestProjectCodeReviewsEndpoint:
    """Test suite for GET /api/projects/{project_id}/code-reviews endpoint."""

    def test_get_project_code_reviews_success(self, api_client, project_with_reviews):
        """Test fetching code reviews for a project."""
        project_id, task_ids, review_ids = project_with_reviews

        response = api_client.get(f"/api/projects/{project_id}/code-reviews")

        assert response.status_code == 200
        data = response.json()

        # Verify response structure (flat structure matching get_task_reviews)
        assert "findings" in data
        assert "total_count" in data
        assert "severity_counts" in data
        assert "category_counts" in data
        assert "has_blocking_findings" in data
        assert "task_id" in data
        assert data["task_id"] is None  # Project-level aggregate

        # Verify findings count
        assert len(data["findings"]) == 6
        assert data["total_count"] == 6

        # Verify severity counts
        assert data["severity_counts"]["critical"] == 1
        assert data["severity_counts"]["high"] == 1
        assert data["severity_counts"]["medium"] == 2
        assert data["severity_counts"]["low"] == 1
        assert data["severity_counts"]["info"] == 1

        # Verify category counts
        assert data["category_counts"]["security"] == 2
        assert data["category_counts"]["performance"] == 1
        assert data["category_counts"]["quality"] == 1
        assert data["category_counts"]["maintainability"] == 1
        assert data["category_counts"]["style"] == 1

        # Verify blocking issues flag
        assert data["has_blocking_findings"] is True  # Has critical + high

    def test_get_project_code_reviews_with_severity_filter(
        self, api_client, project_with_reviews
    ):
        """Test filtering reviews by severity."""
        project_id, task_ids, review_ids = project_with_reviews

        # Filter by critical severity
        response = api_client.get(
            f"/api/projects/{project_id}/code-reviews?severity=critical"
        )

        assert response.status_code == 200
        data = response.json()

        # Should only return critical findings
        assert len(data["findings"]) == 1
        assert data["findings"][0]["severity"] == "critical"
        assert data["total_count"] == 1

    def test_get_project_code_reviews_multiple_severity_filters(
        self, api_client, project_with_reviews
    ):
        """Test filtering by different severity levels."""
        project_id, task_ids, review_ids = project_with_reviews

        # Test each severity level
        severity_expected_counts = {
            "critical": 1,
            "high": 1,
            "medium": 2,
            "low": 1,
            "info": 1
        }

        for severity, expected_count in severity_expected_counts.items():
            response = api_client.get(
                f"/api/projects/{project_id}/code-reviews?severity={severity}"
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data["findings"]) == expected_count
            # Verify all findings have the correct severity
            for finding in data["findings"]:
                assert finding["severity"] == severity

    def test_get_project_code_reviews_empty_project(self, api_client, empty_project):
        """Test fetching reviews for project with no reviews."""
        project_id = empty_project

        response = api_client.get(f"/api/projects/{project_id}/code-reviews")

        assert response.status_code == 200
        data = response.json()

        # Verify empty results
        assert len(data["findings"]) == 0
        assert data["total_count"] == 0
        assert data["has_blocking_findings"] is False

        # Verify all counts are zero
        for severity in ["critical", "high", "medium", "low", "info"]:
            assert data["severity_counts"][severity] == 0

        for category in ["security", "performance", "quality", "maintainability", "style"]:
            assert data["category_counts"][category] == 0

    def test_get_project_code_reviews_invalid_severity(
        self, api_client, project_with_reviews
    ):
        """Test invalid severity filter returns 400."""
        project_id, task_ids, review_ids = project_with_reviews

        response = api_client.get(
            f"/api/projects/{project_id}/code-reviews?severity=invalid"
        )

        assert response.status_code == 400
        assert "Invalid severity" in response.json()["detail"]

    def test_get_project_code_reviews_nonexistent_project(self, api_client):
        """Test fetching reviews for non-existent project returns 404."""
        response = api_client.get("/api/projects/99999/code-reviews")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_project_code_reviews_findings_structure(
        self, api_client, project_with_reviews
    ):
        """Test that findings have correct structure."""
        project_id, task_ids, review_ids = project_with_reviews

        response = api_client.get(f"/api/projects/{project_id}/code-reviews")
        assert response.status_code == 200
        data = response.json()

        # Check first finding has all required fields
        finding = data["findings"][0]
        required_fields = [
            "id", "task_id", "agent_id", "project_id", "file_path",
            "line_number", "severity", "category", "message",
            "recommendation", "code_snippet", "created_at"
        ]

        for field in required_fields:
            assert field in finding, f"Missing field: {field}"

        # Verify field types
        assert isinstance(finding["id"], int)
        assert isinstance(finding["task_id"], int)
        assert isinstance(finding["agent_id"], str)
        assert isinstance(finding["project_id"], int)
        assert finding["project_id"] == project_id

    def test_get_project_code_reviews_no_blocking_issues(
        self, api_client, empty_project
    ):
        """Test project with only low/info findings has no blocking issues."""
        project_id = empty_project

        # Create task with only low severity findings
        task = Task(
            project_id=project_id,
            title="Minor refactoring",
            description="Clean up code",
            status=TaskStatus.IN_PROGRESS
        )
        task_id = get_app().state.db.create_task(task)

        # Add only low severity review
        review = CodeReview(
            task_id=task_id,
            agent_id="review-001",
            project_id=project_id,
            file_path="test.py",
            line_number=10,
            severity=Severity.LOW,
            category=ReviewCategory.STYLE,
            message="Minor style issue",
            recommendation="Fix formatting"
        )
        get_app().state.db.save_code_review(review)

        response = api_client.get(f"/api/projects/{project_id}/code-reviews")
        assert response.status_code == 200
        data = response.json()

        # Should not have blocking issues (only low severity)
        assert data["has_blocking_findings"] is False
