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


class TestBackendWorkerAgentContextBuilding:
    """Test context building from codebase index and database."""

    def test_build_context_with_related_symbols(self, tmp_path):
        """Test build_context queries codebase index for related symbols."""
        from codeframe.indexing.models import Symbol, SymbolType

        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        # Mock symbols returned from codebase index
        mock_symbols = [
            Symbol(
                name="User",
                type=SymbolType.CLASS,
                file_path="codeframe/models/user.py",
                line_number=10,
                language="python",
                parent=None
            ),
            Symbol(
                name="authenticate",
                type=SymbolType.FUNCTION,
                file_path="codeframe/auth/user_auth.py",
                line_number=25,
                language="python",
                parent=None
            )
        ]
        index.search_pattern.return_value = mock_symbols

        agent = BackendWorkerAgent(
            project_id=1,
            db=db,
            codebase_index=index,
            project_root=tmp_path
        )

        task = {
            "id": 1,
            "task_number": "1.5.2",
            "title": "Implement user authentication",
            "description": "Add user login functionality",
            "issue_id": 1,
            "parent_issue_number": "1.5",
            "status": "pending",
            "priority": 0
        }

        context = agent.build_context(task)

        assert context is not None
        assert context["task"] == task
        assert "related_symbols" in context
        assert len(context["related_symbols"]) == 2
        assert context["related_symbols"][0].name == "User"
        assert context["related_symbols"][1].name == "authenticate"

    def test_build_context_with_issue_data(self, tmp_path):
        """Test build_context retrieves parent issue information."""
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        # Mock issue data from database
        mock_issue = {
            "id": 1,
            "issue_number": "1.5",
            "title": "User Authentication System",
            "description": "Complete authentication system",
            "status": "in_progress",
            "priority": 0
        }
        db.get_issue.return_value = mock_issue

        index.search_pattern.return_value = []

        agent = BackendWorkerAgent(
            project_id=1,
            db=db,
            codebase_index=index,
            project_root=tmp_path
        )

        task = {
            "id": 1,
            "task_number": "1.5.2",
            "title": "Implement user authentication",
            "description": "Add user login functionality",
            "issue_id": 1,
            "parent_issue_number": "1.5",
            "status": "pending",
            "priority": 0
        }

        context = agent.build_context(task)

        assert context is not None
        assert "issue_context" in context
        assert context["issue_context"]["title"] == "User Authentication System"
        db.get_issue.assert_called_once_with(1)

    def test_build_context_with_related_files(self, tmp_path):
        """Test build_context identifies related files from symbols."""
        from codeframe.indexing.models import Symbol, SymbolType

        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        mock_symbols = [
            Symbol(
                name="User",
                type=SymbolType.CLASS,
                file_path="codeframe/models/user.py",
                line_number=10,
                language="python",
                parent=None
            ),
            Symbol(
                name="UserAuth",
                type=SymbolType.CLASS,
                file_path="codeframe/auth/user_auth.py",
                line_number=15,
                language="python",
                parent=None
            )
        ]
        index.search_pattern.return_value = mock_symbols
        db.get_issue.return_value = None

        agent = BackendWorkerAgent(
            project_id=1,
            db=db,
            codebase_index=index,
            project_root=tmp_path
        )

        task = {
            "id": 1,
            "task_number": "1.5.2",
            "title": "Implement user authentication",
            "description": "Add user login functionality",
            "issue_id": 1,
            "parent_issue_number": "1.5",
            "status": "pending",
            "priority": 0
        }

        context = agent.build_context(task)

        assert context is not None
        assert "related_files" in context
        assert len(context["related_files"]) == 2
        assert "codeframe/models/user.py" in context["related_files"]
        assert "codeframe/auth/user_auth.py" in context["related_files"]

    def test_build_context_handles_empty_codebase_index(self, tmp_path):
        """Test build_context works when no related symbols found."""
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        index.search_pattern.return_value = []
        db.get_issue.return_value = None

        agent = BackendWorkerAgent(
            project_id=1,
            db=db,
            codebase_index=index,
            project_root=tmp_path
        )

        task = {
            "id": 1,
            "task_number": "1.0.1",
            "title": "Initialize project",
            "description": "Create initial project structure",
            "issue_id": 1,
            "parent_issue_number": "1.0",
            "status": "pending",
            "priority": 0
        }

        context = agent.build_context(task)

        assert context is not None
        assert context["related_symbols"] == []
        assert context["related_files"] == []
        assert context["issue_context"] is None

    def test_build_context_handles_missing_issue_id(self, tmp_path):
        """Test build_context works when issue_id is None."""
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        index.search_pattern.return_value = []

        agent = BackendWorkerAgent(
            project_id=1,
            db=db,
            codebase_index=index,
            project_root=tmp_path
        )

        task = {
            "id": 1,
            "task_number": "1.0.1",
            "title": "Standalone task",
            "description": "No parent issue",
            "issue_id": None,
            "parent_issue_number": None,
            "status": "pending",
            "priority": 0
        }

        context = agent.build_context(task)

        assert context is not None
        assert context["issue_context"] is None
        db.get_issue.assert_not_called()


class TestBackendWorkerAgentCodeGeneration:
    """Test code generation using LLM API."""

    @patch('anthropic.Anthropic')
    def test_generate_code_creates_single_file(self, mock_anthropic_class, tmp_path):
        """Test generate_code returns single file creation."""
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        # Mock Anthropic API response
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        mock_response = Mock()
        mock_response.content = [Mock(text=json.dumps({
            "files": [
                {
                    "path": "codeframe/models/user.py",
                    "action": "create",
                    "content": "class User:\n    pass"
                }
            ],
            "explanation": "Created User model"
        }))]
        mock_client.messages.create.return_value = mock_response

        agent = BackendWorkerAgent(
            project_id=1,
            db=db,
            codebase_index=index,
            api_key="test-key",
            project_root=tmp_path
        )

        context = {
            "task": {
                "title": "Create User model",
                "description": "Create basic User class"
            },
            "related_files": [],
            "related_symbols": [],
            "issue_context": None
        }

        result = agent.generate_code(context)

        assert result is not None
        assert "files" in result
        assert len(result["files"]) == 1
        assert result["files"][0]["path"] == "codeframe/models/user.py"
        assert result["files"][0]["action"] == "create"
        assert "class User" in result["files"][0]["content"]
        assert result["explanation"] == "Created User model"

    @patch('anthropic.Anthropic')
    def test_generate_code_modifies_multiple_files(self, mock_anthropic_class, tmp_path):
        """Test generate_code returns multiple file modifications."""
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        mock_response = Mock()
        mock_response.content = [Mock(text=json.dumps({
            "files": [
                {
                    "path": "codeframe/models/user.py",
                    "action": "modify",
                    "content": "# Updated User model"
                },
                {
                    "path": "tests/test_user.py",
                    "action": "create",
                    "content": "# User tests"
                }
            ],
            "explanation": "Updated User model and added tests"
        }))]
        mock_client.messages.create.return_value = mock_response

        agent = BackendWorkerAgent(
            project_id=1,
            db=db,
            codebase_index=index,
            api_key="test-key",
            project_root=tmp_path
        )

        context = {
            "task": {
                "title": "Add User tests",
                "description": "Create tests for User model"
            },
            "related_files": ["codeframe/models/user.py"],
            "related_symbols": [],
            "issue_context": None
        }

        result = agent.generate_code(context)

        assert len(result["files"]) == 2
        assert result["files"][0]["action"] == "modify"
        assert result["files"][1]["action"] == "create"

    @patch('anthropic.Anthropic')
    def test_generate_code_handles_api_error(self, mock_anthropic_class, tmp_path):
        """Test generate_code handles API errors gracefully."""
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        # Simulate API error
        mock_client.messages.create.side_effect = Exception("API timeout")

        agent = BackendWorkerAgent(
            project_id=1,
            db=db,
            codebase_index=index,
            api_key="test-key",
            project_root=tmp_path
        )

        context = {
            "task": {"title": "Test", "description": "Test"},
            "related_files": [],
            "related_symbols": [],
            "issue_context": None
        }

        with pytest.raises(Exception) as exc_info:
            agent.generate_code(context)

        assert "API timeout" in str(exc_info.value)

    @patch('anthropic.Anthropic')
    def test_generate_code_handles_malformed_response(self, mock_anthropic_class, tmp_path):
        """Test generate_code handles invalid JSON response."""
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        mock_response = Mock()
        mock_response.content = [Mock(text="Invalid JSON {malformed")]
        mock_client.messages.create.return_value = mock_response

        agent = BackendWorkerAgent(
            project_id=1,
            db=db,
            codebase_index=index,
            api_key="test-key",
            project_root=tmp_path
        )

        context = {
            "task": {"title": "Test", "description": "Test"},
            "related_files": [],
            "related_symbols": [],
            "issue_context": None
        }

        with pytest.raises(json.JSONDecodeError):
            agent.generate_code(context)
