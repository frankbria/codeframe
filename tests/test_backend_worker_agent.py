"""
Tests for Backend Worker Agent (cf-41).

Test coverage for autonomous task execution:
- Initialization and configuration
- Task fetching from database
- Context building from codebase index
- Code generation via LLM
- File operations (create/modify/delete)
- Task execution orchestration

Following strict TDD methodology (RED-GREEN-REFACTOR).
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import tempfile
import json

from codeframe.agents.backend_worker_agent import BackendWorkerAgent
from codeframe.persistence.database import Database
from codeframe.indexing.codebase_index import CodebaseIndex
from codeframe.core.models import Task, TaskStatus, ProjectStatus


class TestBackendWorkerAgentInitialization:
    """Test agent initialization and configuration."""

    def test_init_with_required_parameters(self, tmp_path):
        """Test agent initializes with required parameters."""
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        agent = BackendWorkerAgent(
            project_id=1,
            db=db,
            codebase_index=index,
            project_root=tmp_path
        )

        assert agent.project_id == 1
        assert agent.db == db
        assert agent.codebase_index == index
        assert agent.project_root == tmp_path

    def test_init_with_default_provider(self, tmp_path):
        """Test agent defaults to 'claude' provider."""
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        agent = BackendWorkerAgent(
            project_id=1,
            db=db,
            codebase_index=index,
            project_root=tmp_path
        )

        assert agent.provider == "claude"

    def test_init_with_custom_provider(self, tmp_path):
        """Test agent accepts custom provider."""
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        agent = BackendWorkerAgent(
            project_id=1,
            db=db,
            codebase_index=index,
            provider="gpt4",
            project_root=tmp_path
        )

        assert agent.provider == "gpt4"

    def test_init_with_api_key(self, tmp_path):
        """Test agent accepts API key for LLM provider."""
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        agent = BackendWorkerAgent(
            project_id=1,
            db=db,
            codebase_index=index,
            api_key="test-api-key",
            project_root=tmp_path
        )

        assert agent.api_key == "test-api-key"


class TestBackendWorkerAgentTaskFetching:
    """Test task fetching from database."""

    def test_fetch_next_task_returns_pending_task(self, tmp_path):
        """Test fetch_next_task returns highest priority pending task."""
        # Setup database with pending task
        db = Database(":memory:")
        db.initialize()

        project_id = db.create_project("test", ProjectStatus.ACTIVE)

        # Create issue
        issue_id = db.create_issue({
            "project_id": project_id,
            "issue_number": "1.0",
            "title": "Test Issue",
            "status": "pending",
            "priority": 0,
            "workflow_step": 1
        })

        # Create pending task
        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Test Task",
            description="Test description",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
            can_parallelize=False
        )

        index = Mock(spec=CodebaseIndex)
        agent = BackendWorkerAgent(
            project_id=project_id,
            db=db,
            codebase_index=index,
            project_root=tmp_path
        )

        task = agent.fetch_next_task()

        assert task is not None
        assert task["id"] == task_id
        assert task["status"] == "pending"
        assert task["title"] == "Test Task"

    def test_fetch_next_task_returns_none_when_no_tasks(self, tmp_path):
        """Test fetch_next_task returns None when no pending tasks."""
        db = Database(":memory:")
        db.initialize()

        project_id = db.create_project("test", ProjectStatus.ACTIVE)

        index = Mock(spec=CodebaseIndex)
        agent = BackendWorkerAgent(
            project_id=project_id,
            db=db,
            codebase_index=index,
            project_root=tmp_path
        )

        task = agent.fetch_next_task()

        assert task is None

    def test_fetch_next_task_respects_priority_ordering(self, tmp_path):
        """Test fetch_next_task returns highest priority (lowest number) task."""
        db = Database(":memory:")
        db.initialize()

        project_id = db.create_project("test", ProjectStatus.ACTIVE)

        issue_id = db.create_issue({
            "project_id": project_id,
            "issue_number": "1.0",
            "title": "Test Issue",
            "status": "pending",
            "priority": 0,
            "workflow_step": 1
        })

        # Create low priority task (priority=2)
        db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Low Priority Task",
            description="Test",
            status=TaskStatus.PENDING,
            priority=2,
            workflow_step=1,
            can_parallelize=False
        )

        # Create high priority task (priority=0)
        high_priority_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.2",
            parent_issue_number="1.0",
            title="High Priority Task",
            description="Test",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
            can_parallelize=False
        )

        index = Mock(spec=CodebaseIndex)
        agent = BackendWorkerAgent(
            project_id=project_id,
            db=db,
            codebase_index=index,
            project_root=tmp_path
        )

        task = agent.fetch_next_task()

        assert task is not None
        assert task["id"] == high_priority_id
        assert task["title"] == "High Priority Task"

    def test_fetch_next_task_respects_workflow_step_ordering(self, tmp_path):
        """Test fetch_next_task respects workflow_step as secondary sort."""
        db = Database(":memory:")
        db.initialize()

        project_id = db.create_project("test", ProjectStatus.ACTIVE)

        issue_id = db.create_issue({
            "project_id": project_id,
            "issue_number": "1.0",
            "title": "Test Issue",
            "status": "pending",
            "priority": 0,
            "workflow_step": 1
        })

        # Create task with same priority but higher workflow step
        db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Later Workflow Task",
            description="Test",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=5,
            can_parallelize=False
        )

        # Create task with same priority but lower workflow step
        earlier_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.2",
            parent_issue_number="1.0",
            title="Earlier Workflow Task",
            description="Test",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
            can_parallelize=False
        )

        index = Mock(spec=CodebaseIndex)
        agent = BackendWorkerAgent(
            project_id=project_id,
            db=db,
            codebase_index=index,
            project_root=tmp_path
        )

        task = agent.fetch_next_task()

        assert task is not None
        assert task["id"] == earlier_id
        assert task["title"] == "Earlier Workflow Task"

    def test_fetch_next_task_filters_by_project_id(self, tmp_path):
        """Test fetch_next_task only returns tasks for correct project."""
        db = Database(":memory:")
        db.initialize()

        # Create two projects
        project1_id = db.create_project("project1", ProjectStatus.ACTIVE)
        project2_id = db.create_project("project2", ProjectStatus.ACTIVE)

        # Create issue for project 2
        issue2_id = db.create_issue({
            "project_id": project2_id,
            "issue_number": "1.0",
            "title": "Project 2 Issue",
            "status": "pending",
            "priority": 0,
            "workflow_step": 1
        })

        # Create task for project 2
        db.create_task_with_issue(
            project_id=project2_id,
            issue_id=issue2_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Project 2 Task",
            description="Test",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
            can_parallelize=False
        )

        index = Mock(spec=CodebaseIndex)
        # Agent for project 1 (should not see project 2's tasks)
        agent = BackendWorkerAgent(
            project_id=project1_id,
            db=db,
            codebase_index=index,
            project_root=tmp_path
        )

        task = agent.fetch_next_task()

        assert task is None  # Should not return project 2's task

    def test_fetch_next_task_skips_non_pending_tasks(self, tmp_path):
        """Test fetch_next_task only returns pending tasks."""
        db = Database(":memory:")
        db.initialize()

        project_id = db.create_project("test", ProjectStatus.ACTIVE)

        issue_id = db.create_issue({
            "project_id": project_id,
            "issue_number": "1.0",
            "title": "Test Issue",
            "status": "pending",
            "priority": 0,
            "workflow_step": 1
        })

        # Create completed task
        db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Completed Task",
            description="Test",
            status=TaskStatus.COMPLETED,
            priority=0,
            workflow_step=1,
            can_parallelize=False
        )

        # Create in_progress task
        db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.2",
            parent_issue_number="1.0",
            title="In Progress Task",
            description="Test",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            workflow_step=1,
            can_parallelize=False
        )

        index = Mock(spec=CodebaseIndex)
        agent = BackendWorkerAgent(
            project_id=project_id,
            db=db,
            codebase_index=index,
            project_root=tmp_path
        )

        task = agent.fetch_next_task()

        assert task is None  # No pending tasks
