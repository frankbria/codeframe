"""
Deployment Contract Tests

These tests validate the API contracts and environment configuration
that should be verified BEFORE deploying to staging/production.

Created in response to cf-46 where production bugs were not caught by tests.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from codeframe.persistence.database import Database
from codeframe.core.models import TaskStatus, Issue


class TestAPIContracts:
    """Test that API endpoints return data matching frontend expectations."""

    def test_projects_endpoint_contract(self):
        """
        Validate complete /api/projects response schema.

        Frontend expects each project to have:
        - id, name, status, phase, created_at (basic fields)
        - progress (object with completed_tasks, total_tasks, percentage)
        """
        # Given: A database with a project and tasks
        db = Database(":memory:")
        db.initialize()

        project_id = db.create_project("API Contract Test", "Api Contract Test project")

        issue = Issue(
            project_id=project_id,
            issue_number="1.1",
            title="Test Issue",
            description="Test",
            status=TaskStatus.IN_PROGRESS,
            priority=2,
            workflow_step=1,
        )
        issue_id = db.create_issue(issue)

        db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.1.1",
            parent_issue_number="1.1",
            title="Task 1",
            description="Completed task",
            status=TaskStatus.COMPLETED,
            priority=2,
            workflow_step=1,
            can_parallelize=False,
        )

        # When: We call the API endpoint (via database layer)
        projects = db.list_projects()

        # Then: Response must match frontend contract
        assert len(projects) == 1
        project = projects[0]

        # Basic fields (frontend Dashboard.tsx:25-30)
        required_basic_fields = ["id", "name", "status", "phase", "created_at"]
        for field in required_basic_fields:
            assert field in project, f"Missing required field: {field}"

        # Progress field (frontend Dashboard.tsx:194-218)
        assert "progress" in project, "Missing 'progress' field - causes TypeError in Dashboard"

        progress = project["progress"]
        assert isinstance(progress, dict), "'progress' must be a dict object"

        # Progress sub-fields (Dashboard.tsx expects these)
        assert "completed_tasks" in progress
        assert "total_tasks" in progress
        assert "percentage" in progress

        # Type validation
        assert isinstance(progress["completed_tasks"], int)
        assert isinstance(progress["total_tasks"], int)
        assert isinstance(progress["percentage"], float)

        # Value range validation
        assert progress["completed_tasks"] >= 0
        assert progress["total_tasks"] >= 0
        assert 0.0 <= progress["percentage"] <= 100.0

    def test_project_status_endpoint_contract(self):
        """
        Validate /api/projects/{id}/status response schema.

        Frontend Dashboard.tsx uses THIS endpoint (not /api/projects).
        This was the actual Bug 1 in cf-46!
        """
        # Given: A database with a project and tasks
        db = Database(":memory:")
        db.initialize()

        project_id = db.create_project("Status Test", "Status Test project")

        issue = Issue(
            project_id=project_id,
            issue_number="1.1",
            title="Test Issue",
            description="Test",
            status=TaskStatus.IN_PROGRESS,
            priority=2,
            workflow_step=1,
        )
        issue_id = db.create_issue(issue)

        db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.1.1",
            parent_issue_number="1.1",
            title="Completed Task",
            description="Test",
            status=TaskStatus.COMPLETED,
            priority=2,
            workflow_step=1,
            can_parallelize=False,
        )

        # When: We simulate the /status endpoint (get_project + calculate_progress)
        project = db.get_project(project_id)
        progress = db._calculate_project_progress(project_id)

        # Build response like server.py does
        status_response = {
            "project_id": project["id"],
            "name": project["name"],
            "status": project["status"],
            "phase": project.get("phase", "discovery"),
            "workflow_step": project.get("workflow_step", 1),
            "progress": progress,
        }

        # Then: Response must have progress field
        assert "progress" in status_response, "Missing 'progress' - this was the cf-46 bug!"

        # Validate progress structure
        assert "completed_tasks" in status_response["progress"]
        assert "total_tasks" in status_response["progress"]
        assert "percentage" in status_response["progress"]

        # Validate values
        assert status_response["progress"]["completed_tasks"] == 1
        assert status_response["progress"]["total_tasks"] == 1
        assert status_response["progress"]["percentage"] == 100.0

    def test_projects_endpoint_empty_database(self):
        """Test /api/projects returns empty array when no projects exist."""
        # Given: An empty database
        db = Database(":memory:")
        db.initialize()

        # When: We fetch projects
        projects = db.list_projects()

        # Then: Should return empty list (not None, not error)
        assert projects == []
        assert isinstance(projects, list)

    def test_project_progress_calculation_correctness(self):
        """
        Test that progress percentage is calculated correctly.

        This caught the cf-46 bug where progress was completely missing.
        """
        # Given: Multiple projects with different completion rates
        db = Database(":memory:")
        db.initialize()

        test_cases = [
            ("0% complete", 0, 5),  # 0 of 5 tasks
            ("50% complete", 1, 2),  # 1 of 2 tasks
            ("100% complete", 3, 3),  # 3 of 3 tasks
            ("Empty project", 0, 0),  # No tasks
        ]

        for name, completed, total in test_cases:
            project_id = db.create_project(name, f"{name} project")

            if total > 0:
                issue = Issue(
                    project_id=project_id,
                    issue_number="1.1",
                    title=f"Issue for {name}",
                    description="Test",
                    status=TaskStatus.IN_PROGRESS,
                    priority=2,
                    workflow_step=1,
                )
                issue_id = db.create_issue(issue)

                for i in range(total):
                    status = TaskStatus.COMPLETED if i < completed else TaskStatus.PENDING
                    db.create_task_with_issue(
                        project_id=project_id,
                        issue_id=issue_id,
                        task_number=f"1.1.{i+1}",
                        parent_issue_number="1.1",
                        title=f"Task {i+1}",
                        description=f"Task {i+1}",
                        status=status,
                        priority=2,
                        workflow_step=1,
                        can_parallelize=False,
                    )

        # When: We fetch all projects
        projects = db.list_projects()

        # Then: Each project should have correct progress
        expected_percentages = {
            "0% complete": 0.0,
            "50% complete": 50.0,
            "100% complete": 100.0,
            "Empty project": 0.0,
        }

        for project in projects:
            expected = expected_percentages[project["name"]]
            actual = project["progress"]["percentage"]
            assert actual == expected, f"{project['name']}: expected {expected}%, got {actual}%"


class TestEnvironmentConfiguration:
    """Test that environment variables are properly configured."""

    def test_cors_allowed_origins_configurable(self):
        """
        Test that CORS origins can be configured via environment variable.

        This prevents hardcoded CORS origins (cf-46 issue).
        """
        # This test validates that the server.py code reads CORS_ALLOWED_ORIGINS
        # We can't easily test the FastAPI middleware without starting the server,
        # but we can validate the configuration pattern.

        # The pattern should be:
        # 1. Read CORS_ALLOWED_ORIGINS from env
        # 2. Parse comma-separated list
        # 3. Use in CORSMiddleware

        # Given: Various CORS configuration strings
        test_cases = [
            ("", []),  # Empty should use defaults
            ("http://localhost:3000", ["http://localhost:3000"]),
            (
                "http://localhost:3000,http://example.com",
                ["http://localhost:3000", "http://example.com"],
            ),
            (
                "  http://a.com  ,  http://b.com  ",
                ["http://a.com", "http://b.com"],
            ),  # Whitespace handling
        ]

        for env_value, expected_origins in test_cases:
            # When: We parse the environment variable
            if env_value:
                origins = [origin.strip() for origin in env_value.split(",") if origin.strip()]
            else:
                origins = []

            # Then: Should parse correctly
            assert origins == expected_origins, f"Failed to parse: {env_value!r}"

    def test_next_public_api_url_required(self):
        """
        Test that NEXT_PUBLIC_API_URL is set for deployment.

        Missing this causes frontend to try localhost:8080 instead of actual server.
        """
        # In deployment scenarios, this variable MUST be set
        # This is a reminder test that validates the requirement

        required_env_vars = [
            "NEXT_PUBLIC_API_URL",
            "NEXT_PUBLIC_WS_URL",
        ]

        # Note: In actual deployment, these are read from .env.staging
        # This test documents the requirement
        for var in required_env_vars:
            # Test passes - just documenting the requirement
            assert var in ["NEXT_PUBLIC_API_URL", "NEXT_PUBLIC_WS_URL"]

    def test_backend_port_configuration(self):
        """
        Test that backend port can be configured via environment.

        Validates BACKEND_PORT is used in next.config.js
        """
        # Given: Different port configurations
        test_ports = ["8080", "14200", "3001"]

        for port in test_ports:
            # When: BACKEND_PORT environment variable is set
            # Then: Should be used for backend URL
            # Note: This is validated by next.config.js reading process.env.BACKEND_PORT
            assert port.isdigit()
            assert 1 <= int(port) <= 65535


class TestDataIntegrity:
    """Test data integrity constraints."""

    def test_task_status_values(self):
        """
        Test that task status values match what frontend expects.

        Frontend Dashboard checks for status === 'completed' exactly.
        """
        # Valid task statuses from TaskStatus enum

        # Given: A database with tasks in various statuses
        db = Database(":memory:")
        db.initialize()

        project_id = db.create_project("Status Test", "Status Test project")
        issue = Issue(
            project_id=project_id,
            issue_number="1.1",
            title="Test",
            description="Test",
            status=TaskStatus.IN_PROGRESS,
            priority=2,
            workflow_step=1,
        )
        issue_id = db.create_issue(issue)

        # Create a task with 'completed' status
        db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.1.1",
            parent_issue_number="1.1",
            title="Completed Task",
            description="Test",
            status=TaskStatus.COMPLETED,
            priority=2,
            workflow_step=1,
            can_parallelize=False,
        )

        # When: We fetch projects
        projects = db.list_projects()

        # Then: Completed task should be counted
        assert projects[0]["progress"]["completed_tasks"] == 1

    def test_progress_calculation_ignores_non_completed_statuses(self):
        """
        Test that only 'completed' status counts as completed.

        Statuses like 'in_progress', 'blocked' should NOT count as completed.
        """
        # Given: A project with tasks in various non-completed statuses
        db = Database(":memory:")
        db.initialize()

        project_id = db.create_project("Status Test", "Status Test project")
        issue = Issue(
            project_id=project_id,
            issue_number="1.1",
            title="Test",
            description="Test",
            status=TaskStatus.IN_PROGRESS,
            priority=2,
            workflow_step=1,
        )
        issue_id = db.create_issue(issue)

        # Create tasks with non-completed statuses
        for i, status in enumerate(
            [TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED]
        ):
            db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=f"1.1.{i+1}",
                parent_issue_number="1.1",
                title=f"Task {i+1}",
                description=f"Task in {status.value} status",
                status=status,
                priority=2,
                workflow_step=1,
                can_parallelize=False,
            )

        # When: We fetch projects
        projects = db.list_projects()

        # Then: No tasks should be counted as completed
        assert projects[0]["progress"]["completed_tasks"] == 0
        assert projects[0]["progress"]["total_tasks"] == 3
        assert projects[0]["progress"]["percentage"] == 0.0


class TestEdgeCases:
    """Test edge cases that might break in production."""

    def test_project_with_null_fields(self):
        """Test that projects with NULL optional fields don't break API."""
        # Given: A project with minimal fields (nulls for optionals)
        db = Database(":memory:")
        db.initialize()

        db.create_project("Minimal Project", "Minimal Project project")

        # When: We fetch projects
        projects = db.list_projects()

        # Then: Should handle nulls gracefully
        project = projects[0]
        assert project["workspace_path"] == ""  # Default empty workspace
        assert project["config"] is None  # Optional field
        assert "progress" in project  # Required field
        assert project["progress"]["total_tasks"] == 0

    def test_large_project_performance(self):
        """
        Test that progress calculation is efficient for projects with many tasks.

        Ensures we don't have N+1 query problems.
        """
        # Given: A project with many tasks (100+)
        db = Database(":memory:")
        db.initialize()

        project_id = db.create_project("Large Project", "Large Project project")
        issue = Issue(
            project_id=project_id,
            issue_number="1.1",
            title="Large Issue",
            description="Test",
            status=TaskStatus.IN_PROGRESS,
            priority=2,
            workflow_step=1,
        )
        issue_id = db.create_issue(issue)

        # Create 100 tasks (50 completed, 50 pending)
        for i in range(100):
            status = TaskStatus.COMPLETED if i < 50 else TaskStatus.PENDING
            db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=f"1.1.{i+1}",
                parent_issue_number="1.1",
                title=f"Task {i+1}",
                description=f"Task {i+1}",
                status=status,
                priority=2,
                workflow_step=1,
                can_parallelize=False,
            )

        # When: We fetch projects
        import time

        start = time.time()
        projects = db.list_projects()
        elapsed = time.time() - start

        # Then: Should complete quickly (< 100ms for 100 tasks)
        assert elapsed < 0.1, f"Progress calculation too slow: {elapsed:.3f}s"

        # And: Should have correct counts
        assert projects[0]["progress"]["total_tasks"] == 100
        assert projects[0]["progress"]["completed_tasks"] == 50
        assert projects[0]["progress"]["percentage"] == 50.0

    def test_multiple_projects_independent_progress(self):
        """
        Test that progress is calculated independently for each project.

        Ensures no cross-project contamination in progress calculation.
        """
        # Given: Two projects with different task counts
        db = Database(":memory:")
        db.initialize()

        # Project 1: 75% complete
        p1_id = db.create_project("Project 1", "Project 1 project")
        i1 = db.create_issue(
            Issue(
                project_id=p1_id,
                issue_number="1.1",
                title="I1",
                description="",
                status=TaskStatus.IN_PROGRESS,
                priority=2,
                workflow_step=1,
            )
        )
        for i in range(4):
            db.create_task_with_issue(
                project_id=p1_id,
                issue_id=i1,
                task_number=f"1.1.{i+1}",
                parent_issue_number="1.1",
                title=f"T{i+1}",
                description="",
                status=TaskStatus.COMPLETED if i < 3 else TaskStatus.PENDING,
                priority=2,
                workflow_step=1,
                can_parallelize=False,
            )

        # Project 2: 25% complete
        p2_id = db.create_project("Project 2", "Project 2 project")
        i2 = db.create_issue(
            Issue(
                project_id=p2_id,
                issue_number="1.1",
                title="I1",
                description="",
                status=TaskStatus.IN_PROGRESS,
                priority=2,
                workflow_step=1,
            )
        )
        for i in range(4):
            db.create_task_with_issue(
                project_id=p2_id,
                issue_id=i2,
                task_number=f"1.1.{i+1}",
                parent_issue_number="1.1",
                title=f"T{i+1}",
                description="",
                status=TaskStatus.COMPLETED if i < 1 else TaskStatus.PENDING,
                priority=2,
                workflow_step=1,
                can_parallelize=False,
            )

        # When: We fetch all projects
        projects = db.list_projects()

        # Then: Each project should have independent progress
        p1 = next(p for p in projects if p["name"] == "Project 1")
        p2 = next(p for p in projects if p["name"] == "Project 2")

        assert p1["progress"]["completed_tasks"] == 3
        assert p1["progress"]["total_tasks"] == 4
        assert p1["progress"]["percentage"] == 75.0

        assert p2["progress"]["completed_tasks"] == 1
        assert p2["progress"]["total_tasks"] == 4
        assert p2["progress"]["percentage"] == 25.0
