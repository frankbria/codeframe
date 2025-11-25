"""Tests for Quality Gates and Checkpoint API endpoints (Sprint 10).

Covers quality gate status checking, checkpoint creation/restoration, and cost metrics.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path
import tempfile
import json

from codeframe.core.models import (
    TaskStatus,
    Task,
    AgentMaturity,
)


def get_app():
    """Get the current app instance after module reload."""
    from codeframe.ui.server import app
    return app


class TestGetQualityGateStatus:
    """Test GET /api/tasks/{task_id}/quality-gates endpoint."""

    def test_get_quality_gate_status_success(self, api_client):
        """Test getting quality gate status for a task."""
        # Arrange: Create project and task
        project_id = get_app().state.db.create_project(
            name="Test Quality Gates",
            description="Test quality gate status"
        )

        task = Task(
            project_id=project_id,
            title="Test Task",
            description="Task with quality gates",
            status=TaskStatus.IN_PROGRESS,
            priority=1,
            workflow_step=10,
        )
        task_id = get_app().state.db.create_task(task)

        # Act
        response = api_client.get(f"/api/tasks/{task_id}/quality-gates")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert "status" in data
        assert data["task_id"] == task_id

    def test_get_quality_gate_status_task_not_found(self, api_client):
        """Test getting quality gates for non-existent task."""
        # Act
        response = api_client.get("/api/tasks/99999/quality-gates")

        # Assert
        assert response.status_code == 404


class TestTriggerQualityGates:
    """Test POST /api/tasks/{task_id}/quality-gates endpoint."""

    def test_trigger_quality_gates_success(self, api_client):
        """Test manually triggering quality gates."""
        # Arrange: Create project and task
        project_id = get_app().state.db.create_project(
            name="Test Trigger Gates",
            description="Test triggering quality gates",
            project_path="/tmp/test-quality-gates"
        )

        task = Task(
            project_id=project_id,
            title="Test Task",
            description="Task to test quality gates",
            status=TaskStatus.IN_PROGRESS,
            priority=1,
            workflow_step=10,
        )
        task_id = get_app().state.db.create_task(task)

        # Mock quality gate runner
        with patch('codeframe.lib.quality_gates.QualityGateRunner') as mock_runner_class:
            mock_runner = Mock()
            mock_runner.run_all_gates.return_value = {
                "status": "passed",
                "failures": [],
                "execution_time_seconds": 1.5
            }
            mock_runner_class.return_value = mock_runner

            # Act
            response = api_client.post(
                f"/api/tasks/{task_id}/quality-gates",
                json={}
            )

            # Assert
            assert response.status_code == 202
            data = response.json()
            assert "message" in data

    def test_trigger_quality_gates_task_not_found(self, api_client):
        """Test triggering gates for non-existent task."""
        # Act
        response = api_client.post("/api/tasks/99999/quality-gates", json={})

        # Assert
        assert response.status_code == 404


class TestListCheckpoints:
    """Test GET /api/projects/{id}/checkpoints endpoint."""

    def test_list_checkpoints_success(self, api_client):
        """Test listing checkpoints for a project."""
        # Arrange: Create project
        project_id = get_app().state.db.create_project(
            name="Test Checkpoints",
            description="Test checkpoint listing",
            project_path="/tmp/test-checkpoints"
        )

        # Act
        response = api_client.get(f"/api/projects/{project_id}/checkpoints")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "checkpoints" in data
        assert isinstance(data["checkpoints"], list)

    def test_list_checkpoints_project_not_found(self, api_client):
        """Test listing checkpoints for non-existent project."""
        # Act
        response = api_client.get("/api/projects/99999/checkpoints")

        # Assert
        assert response.status_code == 404


class TestCreateCheckpoint:
    """Test POST /api/projects/{id}/checkpoints endpoint."""

    def test_create_checkpoint_success(self, api_client):
        """Test creating a checkpoint."""
        # Arrange: Create project with path
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir) / "test-project"
            project_path.mkdir()

            # Initialize git repo
            import subprocess
            subprocess.run(["git", "init"], cwd=project_path, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=project_path,
                check=True,
                capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=project_path,
                check=True,
                capture_output=True
            )

            # Create initial commit
            (project_path / "README.md").write_text("# Test Project")
            subprocess.run(["git", "add", "."], cwd=project_path, check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=project_path,
                check=True,
                capture_output=True
            )

            project_id = get_app().state.db.create_project(
                name="Test Create Checkpoint",
                description="Test checkpoint creation",
                project_path=str(project_path)
            )

            # Act
            response = api_client.post(
                f"/api/projects/{project_id}/checkpoints",
                json={
                    "name": "Before refactor",
                    "description": "Stable state before refactoring"
                }
            )

            # Assert
            assert response.status_code == 201
            data = response.json()
            assert "id" in data
            assert data["name"] == "Before refactor"
            assert data["description"] == "Stable state before refactoring"

    def test_create_checkpoint_missing_name(self, api_client):
        """Test creating checkpoint without name."""
        project_id = get_app().state.db.create_project(
            name="Test Missing Name",
            description="Test missing name",
            project_path="/tmp/test-missing-name"
        )

        # Act
        response = api_client.post(
            f"/api/projects/{project_id}/checkpoints",
            json={"description": "No name provided"}
        )

        # Assert
        assert response.status_code == 422

    def test_create_checkpoint_project_not_found(self, api_client):
        """Test creating checkpoint for non-existent project."""
        # Act
        response = api_client.post(
            "/api/projects/99999/checkpoints",
            json={"name": "Test", "description": "Test"}
        )

        # Assert
        assert response.status_code == 404


class TestGetCheckpoint:
    """Test GET /api/projects/{id}/checkpoints/{checkpoint_id} endpoint."""

    def test_get_checkpoint_success(self, api_client):
        """Test getting a specific checkpoint."""
        # Arrange: Create project and checkpoint
        project_id = get_app().state.db.create_project(
            name="Test Get Checkpoint",
            description="Test getting checkpoint",
            project_path="/tmp/test-get-checkpoint"
        )

        # Create checkpoint
        checkpoint_id = get_app().state.db.save_checkpoint(
            project_id=project_id,
            name="Test Checkpoint",
            description="Test checkpoint",
            git_commit="abc123",
            database_backup_path="/tmp/backup.db",
            context_snapshot={"items": []},
            trigger="manual"
        )

        # Act
        response = api_client.get(
            f"/api/projects/{project_id}/checkpoints/{checkpoint_id}"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == checkpoint_id
        assert data["name"] == "Test Checkpoint"

    def test_get_checkpoint_not_found(self, api_client):
        """Test getting non-existent checkpoint."""
        project_id = get_app().state.db.create_project(
            name="Test Not Found",
            description="Test checkpoint not found",
            project_path="/tmp/test-not-found"
        )

        # Act
        response = api_client.get(
            f"/api/projects/{project_id}/checkpoints/99999"
        )

        # Assert
        assert response.status_code == 404


class TestDeleteCheckpoint:
    """Test DELETE /api/projects/{id}/checkpoints/{checkpoint_id} endpoint."""

    def test_delete_checkpoint_success(self, api_client):
        """Test deleting a checkpoint."""
        # Arrange: Create project and checkpoint
        project_id = get_app().state.db.create_project(
            name="Test Delete Checkpoint",
            description="Test deleting checkpoint",
            project_path="/tmp/test-delete-checkpoint"
        )

        checkpoint_id = get_app().state.db.save_checkpoint(
            project_id=project_id,
            name="To Delete",
            description="Checkpoint to delete",
            git_commit="def456",
            database_backup_path="/tmp/to-delete.db",
            context_snapshot={"items": []},
            trigger="manual"
        )

        # Act
        response = api_client.delete(
            f"/api/projects/{project_id}/checkpoints/{checkpoint_id}"
        )

        # Assert
        assert response.status_code == 204

        # Verify deletion
        checkpoint = get_app().state.db.get_checkpoint(checkpoint_id)
        assert checkpoint is None

    def test_delete_checkpoint_not_found(self, api_client):
        """Test deleting non-existent checkpoint."""
        project_id = get_app().state.db.create_project(
            name="Test Delete Not Found",
            description="Test delete not found",
            project_path="/tmp/test-delete-not-found"
        )

        # Act
        response = api_client.delete(
            f"/api/projects/{project_id}/checkpoints/99999"
        )

        # Assert
        assert response.status_code == 404


class TestRestoreCheckpoint:
    """Test POST /api/projects/{id}/checkpoints/{checkpoint_id}/restore endpoint."""

    def test_restore_checkpoint_success(self, api_client):
        """Test restoring a checkpoint."""
        # Arrange: Create project with git repo
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir) / "test-restore"
            project_path.mkdir()

            # Initialize git repo
            import subprocess
            subprocess.run(["git", "init"], cwd=project_path, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=project_path,
                check=True,
                capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=project_path,
                check=True,
                capture_output=True
            )

            # Create initial commit
            (project_path / "file.txt").write_text("version 1")
            subprocess.run(["git", "add", "."], cwd=project_path, check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "Version 1"],
                cwd=project_path,
                check=True,
                capture_output=True
            )

            # Get commit hash
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=project_path,
                check=True,
                capture_output=True,
                text=True
            )
            commit_hash = result.stdout.strip()

            project_id = get_app().state.db.create_project(
                name="Test Restore",
                description="Test checkpoint restoration",
                project_path=str(project_path)
            )

            # Create checkpoint
            checkpoint_id = get_app().state.db.save_checkpoint(
                project_id=project_id,
                name="Version 1",
                description="Checkpoint at version 1",
                git_commit=commit_hash,
                database_backup_path=str(get_app().state.db.db_path),
                context_snapshot={"items": []},
                trigger="manual"
            )

            # Make another commit
            (project_path / "file.txt").write_text("version 2")
            subprocess.run(["git", "add", "."], cwd=project_path, check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "Version 2"],
                cwd=project_path,
                check=True,
                capture_output=True
            )

            # Act: Restore to checkpoint
            response = api_client.post(
                f"/api/projects/{project_id}/checkpoints/{checkpoint_id}/restore",
                json={}
            )

            # Assert
            assert response.status_code == 202
            data = response.json()
            assert "message" in data

    def test_restore_checkpoint_not_found(self, api_client):
        """Test restoring non-existent checkpoint."""
        project_id = get_app().state.db.create_project(
            name="Test Restore Not Found",
            description="Test restore not found",
            project_path="/tmp/test-restore-not-found"
        )

        # Act
        response = api_client.post(
            f"/api/projects/{project_id}/checkpoints/99999/restore",
            json={}
        )

        # Assert
        assert response.status_code == 404


class TestGetTaskReviews:
    """Test GET /api/tasks/{task_id}/reviews endpoint."""

    def test_get_task_reviews_success(self, api_client):
        """Test getting reviews for a task."""
        # Arrange: Create project and task
        project_id = get_app().state.db.create_project(
            name="Test Reviews",
            description="Test getting reviews"
        )

        task = Task(
            project_id=project_id,
            title="Reviewed Task",
            description="Task with reviews",
            status=TaskStatus.IN_PROGRESS,
            priority=1,
            workflow_step=10,
        )
        task_id = get_app().state.db.create_task(task)

        # Create review
        get_app().state.db.save_code_review(
            task_id=task_id,
            agent_id="review-agent",
            file_path="/tmp/test.py",
            overall_score=75,
            findings=[
                {
                    "severity": "medium",
                    "category": "style",
                    "message": "Line too long",
                    "line": 10
                }
            ],
            status="changes_requested"
        )

        # Act
        response = api_client.get(f"/api/tasks/{task_id}/reviews")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "reviews" in data
        assert len(data["reviews"]) >= 1

    def test_get_task_reviews_with_severity_filter(self, api_client):
        """Test getting reviews filtered by severity."""
        # Arrange
        project_id = get_app().state.db.create_project(
            name="Test Severity Filter",
            description="Test severity filtering"
        )

        task = Task(
            project_id=project_id,
            title="Task",
            description="Task",
            status=TaskStatus.IN_PROGRESS,
            priority=1,
            workflow_step=10,
        )
        task_id = get_app().state.db.create_task(task)

        # Act
        response = api_client.get(
            f"/api/tasks/{task_id}/reviews",
            params={"severity": "critical"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "reviews" in data

    def test_get_task_reviews_task_not_found(self, api_client):
        """Test getting reviews for non-existent task."""
        # Act
        response = api_client.get("/api/tasks/99999/reviews")

        # Assert
        assert response.status_code == 404


class TestAnalyzeCodeReview:
    """Test POST /api/agents/review/analyze endpoint."""

    def test_analyze_code_review_success(self, api_client):
        """Test triggering code review analysis."""
        # Arrange: Create project and task with file
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir) / "test-analyze"
            project_path.mkdir()

            test_file = project_path / "test.py"
            test_file.write_text("def hello(): pass")

            project_id = get_app().state.db.create_project(
                name="Test Analyze",
                description="Test code review analysis",
                project_path=str(project_path)
            )

            task = Task(
                project_id=project_id,
                title="Analyze Task",
                description="Task to analyze",
                status=TaskStatus.IN_PROGRESS,
                priority=1,
                workflow_step=10,
            )
            task_id = get_app().state.db.create_task(task)

            # Act
            with patch('codeframe.lib.review_agent.ReviewAgent') as mock_review_class:
                mock_reviewer = Mock()
                mock_reviewer.analyze_files.return_value = {
                    "status": "approved",
                    "overall_score": 95,
                    "findings": []
                }
                mock_review_class.return_value = mock_reviewer

                response = api_client.post(
                    "/api/agents/review/analyze",
                    json={
                        "task_id": task_id,
                        "project_id": project_id,
                        "files_modified": [str(test_file)]
                    }
                )

                # Assert
                assert response.status_code == 202
                data = response.json()
                assert "message" in data

    def test_analyze_code_review_missing_fields(self, api_client):
        """Test analyze endpoint with missing required fields."""
        # Act
        response = api_client.post(
            "/api/agents/review/analyze",
            json={}
        )

        # Assert
        assert response.status_code == 422
