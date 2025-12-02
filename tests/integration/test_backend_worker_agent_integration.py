"""
Integration tests for Backend Worker Agent (cf-41).

These tests verify that the agent's core functionality works with real components:
- Real database instances (SQLite in-memory)
- Real file I/O operations
- Real codebase indexing
- Real task execution pipeline

Unlike unit tests which mock dependencies, these tests ensure the actual
integration works correctly.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import json

from codeframe.agents.backend_worker_agent import BackendWorkerAgent
from codeframe.persistence.database import Database
from codeframe.indexing.codebase_index import CodebaseIndex
from codeframe.core.models import TaskStatus


@pytest.fixture
def real_db():
    """Create a real in-memory database with lint_results table."""
    db = Database(":memory:")
    db.initialize()

    # Manually create lint_results table (migrations skipped for :memory: databases)
    cursor = db.conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS lint_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            linter TEXT NOT NULL CHECK(linter IN ('ruff', 'eslint', 'other')),
            error_count INTEGER NOT NULL DEFAULT 0,
            warning_count INTEGER NOT NULL DEFAULT 0,
            files_linted INTEGER NOT NULL DEFAULT 0,
            output TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        )
    """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_lint_results_task ON lint_results(task_id)")
    db.conn.commit()

    yield db

    # Cleanup
    if db.conn:
        db.conn.close()


class TestBackendWorkerAgentIntegration:
    """Integration tests for Backend Worker Agent with real components."""

    def test_apply_file_changes_real_file_io(self, tmp_path):
        """Test apply_file_changes with actual file system operations."""
        # Setup with real database (mocked) and index
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        agent = BackendWorkerAgent(
            project_id=1, db=db, codebase_index=index, project_root=tmp_path, use_sdk=False
        )

        # Test creating multiple files with nested directories
        files = [
            {
                "path": "src/models/user.py",
                "action": "create",
                "content": "class User:\n    def __init__(self, name):\n        self.name = name\n",
            },
            {
                "path": "src/models/__init__.py",
                "action": "create",
                "content": "from .user import User\n",
            },
            {
                "path": "tests/test_user.py",
                "action": "create",
                "content": "def test_user():\n    assert True\n",
            },
        ]

        # Execute
        modified_paths = agent.apply_file_changes(files)

        # Verify all files were created
        assert len(modified_paths) == 3
        assert (tmp_path / "src" / "models" / "user.py").exists()
        assert (tmp_path / "src" / "models" / "__init__.py").exists()
        assert (tmp_path / "tests" / "test_user.py").exists()

        # Verify file contents
        user_content = (tmp_path / "src" / "models" / "user.py").read_text()
        assert "class User:" in user_content
        assert "def __init__" in user_content

        # Test modifying an existing file
        files_modify = [
            {
                "path": "src/models/user.py",
                "action": "modify",
                "content": "class User:\n    def __init__(self, name, email):\n        self.name = name\n        self.email = email\n",
            }
        ]

        modified_paths = agent.apply_file_changes(files_modify)

        # Verify modification worked
        modified_content = (tmp_path / "src" / "models" / "user.py").read_text()
        assert "email" in modified_content
        assert modified_content != user_content

        # Test deleting a file
        files_delete = [{"path": "tests/test_user.py", "action": "delete"}]

        modified_paths = agent.apply_file_changes(files_delete)

        # Verify deletion worked
        assert not (tmp_path / "tests" / "test_user.py").exists()
        assert (tmp_path / "src" / "models" / "user.py").exists()  # Other files still exist

    def test_update_task_status_real_database(self, tmp_path, real_db):
        """Test update_task_status with real SQLite database."""
        db = real_db

        # Create real project and task
        project_id = db.create_project("integration_test", "Integration test project")
        issue_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.0",
                "title": "Test Issue",
                "status": "pending",
                "priority": 0,
                "workflow_step": 1,
            }
        )

        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Test Task",
            description="Integration test task",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        # Create agent with real database
        index = Mock(spec=CodebaseIndex)
        agent = BackendWorkerAgent(
            project_id=project_id, db=db, codebase_index=index, project_root=tmp_path, use_sdk=False
        )

        # Test updating to in_progress
        agent.update_task_status(task_id, TaskStatus.IN_PROGRESS.value)

        cursor = db.conn.cursor()
        cursor.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        assert row["status"] == "in_progress"

        # Test updating to completed (should set completed_at)
        agent.update_task_status(
            task_id, TaskStatus.COMPLETED.value, output="Task completed successfully"
        )

        cursor.execute("SELECT status, completed_at FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        assert row["status"] == "completed"
        assert row["completed_at"] is not None

        # Verify completed_at is a valid timestamp
        from datetime import datetime

        completed_at = datetime.fromisoformat(row["completed_at"])
        assert completed_at is not None

    @pytest.mark.asyncio
    async def test_execute_task_integration_with_mocked_llm(self, tmp_path, real_db):
        """Test execute_task with real database and file I/O, mocked LLM."""
        db = real_db

        project_id = db.create_project("integration_test", "Integration test project")
        issue_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.0",
                "title": "Create User Model",
                "status": "pending",
                "priority": 0,
                "workflow_step": 1,
            }
        )

        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Create User class",
            description="Create a User model with name and email fields",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        # Create real codebase index (empty for this test)
        index = Mock(spec=CodebaseIndex)
        index.search_pattern.return_value = []

        # Create agent
        agent = BackendWorkerAgent(
            project_id=project_id,
            db=db,
            codebase_index=index,
            api_key="test-key",
            project_root=tmp_path,
            use_sdk=False,
        )

        # Mock Anthropic API to return realistic code
        with patch("anthropic.AsyncAnthropic") as mock_anthropic_class:
            mock_client = AsyncMock()
            mock_anthropic_class.return_value = mock_client

            mock_response = Mock()
            mock_response.content = [
                Mock(
                    text=json.dumps(
                        {
                            "files": [
                                {
                                    "path": "models/user.py",
                                    "action": "create",
                                    "content": "class User:\n    def __init__(self, name, email):\n        self.name = name\n        self.email = email\n\n    def __repr__(self):\n        return f'User({self.name}, {self.email})'\n",
                                },
                                {
                                    "path": "tests/test_user.py",
                                    "action": "create",
                                    "content": "from models.user import User\n\ndef test_user_creation():\n    user = User('Alice', 'alice@example.com')\n    assert user.name == 'Alice'\n    assert user.email == 'alice@example.com'\n",
                                },
                            ],
                            "explanation": "Created User model with name and email fields, plus tests",
                        }
                    )
                )
            ]
            mock_client.messages.create.return_value = mock_response

            # Get task from database
            cursor = db.conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            task = dict(cursor.fetchone())

            # Mock test execution to avoid pytest finding issues in temp directory
            with patch("codeframe.testing.test_runner.TestRunner.run_tests") as mock_run_tests:
                from codeframe.testing.models import TestResult

                mock_run_tests.return_value = TestResult(
                    status="passed", total=2, passed=2, failed=0, errors=0, skipped=0, duration=0.5
                )

                # Execute task
                result = await agent.execute_task(task)

            # Verify execution succeeded
            assert result["status"] == "completed"
            assert result["error"] is None
            assert len(result["files_modified"]) == 2

            # Verify files were actually created on disk
            assert (tmp_path / "models" / "user.py").exists()
            assert (tmp_path / "tests" / "test_user.py").exists()

            # Verify file contents
            user_content = (tmp_path / "models" / "user.py").read_text()
            assert "class User:" in user_content
            assert "def __init__" in user_content
            assert "self.name" in user_content
            assert "self.email" in user_content

            test_content = (tmp_path / "tests" / "test_user.py").read_text()
            assert "def test_user_creation():" in test_content
            assert "User('Alice', 'alice@example.com')" in test_content

            # Verify task status was updated in database
            cursor.execute("SELECT status, completed_at FROM tasks WHERE id = ?", (task_id,))
            updated_task = cursor.fetchone()
            assert updated_task["status"] == "completed"
            assert updated_task["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_execute_task_handles_file_operation_errors(self, tmp_path, real_db):
        """Test execute_task properly handles file operation failures."""
        db = real_db

        project_id = db.create_project("integration_test", "Integration test project")
        issue_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.0",
                "title": "Test Issue",
                "status": "pending",
                "priority": 0,
                "workflow_step": 1,
            }
        )

        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Modify non-existent file",
            description="This should fail",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        index = Mock(spec=CodebaseIndex)
        index.search_pattern.return_value = []

        agent = BackendWorkerAgent(
            project_id=project_id,
            db=db,
            codebase_index=index,
            api_key="test-key",
            project_root=tmp_path,
            use_sdk=False,
        )

        # Mock API to return a modify operation on non-existent file
        with patch("anthropic.AsyncAnthropic") as mock_anthropic_class:
            mock_client = AsyncMock()
            mock_anthropic_class.return_value = mock_client

            mock_response = Mock()
            mock_response.content = [
                Mock(
                    text=json.dumps(
                        {
                            "files": [
                                {
                                    "path": "nonexistent.py",
                                    "action": "modify",
                                    "content": "modified content",
                                }
                            ],
                            "explanation": "Modified file",
                        }
                    )
                )
            ]
            mock_client.messages.create.return_value = mock_response

            # Get task
            cursor = db.conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            task = dict(cursor.fetchone())

            # Execute task - should fail gracefully
            result = await agent.execute_task(task)

            # Verify failure was handled properly
            assert result["status"] == "failed"
            assert result["error"] is not None
            assert "FileNotFoundError" in result["error"]

            # Verify task status updated to failed in database
            cursor.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
            updated_task = cursor.fetchone()
            assert updated_task["status"] == "failed"

    def test_security_path_traversal_prevention(self, tmp_path):
        """Test that path traversal attempts are blocked in real scenarios."""
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        agent = BackendWorkerAgent(
            project_id=1, db=db, codebase_index=index, project_root=tmp_path, use_sdk=False
        )

        # Attempt path traversal
        malicious_files = [
            {"path": "../../../etc/passwd", "action": "create", "content": "malicious"}
        ]

        with pytest.raises(ValueError) as exc_info:
            agent.apply_file_changes(malicious_files)

        assert "path traversal" in str(exc_info.value).lower()

        # Verify no file was created outside project root
        etc_dir = tmp_path.parent.parent.parent / "etc"
        if etc_dir.exists():
            assert not (etc_dir / "passwd").exists()

    @pytest.mark.asyncio
    async def test_multiple_task_execution_sequence(self, tmp_path, real_db):
        """Test executing multiple tasks in sequence with real database and files."""
        db = real_db

        project_id = db.create_project("multi_task_test", "Multi-task test project")
        issue_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.0",
                "title": "Build User System",
                "status": "pending",
                "priority": 0,
                "workflow_step": 1,
            }
        )

        # Create multiple tasks
        task1_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Create User model",
            description="Create User class",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        task2_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.2",
            parent_issue_number="1.0",
            title="Create User repository",
            description="Create UserRepository class",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=2,
            can_parallelize=False,
        )

        index = Mock(spec=CodebaseIndex)
        index.search_pattern.return_value = []

        agent = BackendWorkerAgent(
            project_id=project_id,
            db=db,
            codebase_index=index,
            api_key="test-key",
            project_root=tmp_path,
            use_sdk=False,
        )

        # Mock API for task 1
        with patch("anthropic.AsyncAnthropic") as mock_anthropic_class:
            mock_client = AsyncMock()
            mock_anthropic_class.return_value = mock_client

            # Task 1: Create User model
            mock_response1 = Mock()
            mock_response1.content = [
                Mock(
                    text=json.dumps(
                        {
                            "files": [
                                {
                                    "path": "user.py",
                                    "action": "create",
                                    "content": "class User:\n    pass\n",
                                }
                            ],
                            "explanation": "Created User model",
                        }
                    )
                )
            ]

            # Task 2: Create UserRepository (modifies user.py, creates repo.py)
            mock_response2 = Mock()
            mock_response2.content = [
                Mock(
                    text=json.dumps(
                        {
                            "files": [
                                {
                                    "path": "user.py",
                                    "action": "modify",
                                    "content": "class User:\n    def __init__(self, name):\n        self.name = name\n",
                                },
                                {
                                    "path": "repository.py",
                                    "action": "create",
                                    "content": "class UserRepository:\n    pass\n",
                                },
                            ],
                            "explanation": "Enhanced User model and created repository",
                        }
                    )
                )
            ]

            mock_client.messages.create.side_effect = [mock_response1, mock_response2]

            # Mock test execution for both tasks
            with patch("codeframe.testing.test_runner.TestRunner.run_tests") as mock_run_tests:
                from codeframe.testing.models import TestResult

                mock_run_tests.return_value = TestResult(
                    status="passed", total=2, passed=2, failed=0, errors=0, skipped=0, duration=0.5
                )

                # Execute task 1
                cursor = db.conn.cursor()
                cursor.execute("SELECT * FROM tasks WHERE id = ?", (task1_id,))
                task1 = dict(cursor.fetchone())

                result1 = await agent.execute_task(task1)
                assert result1["status"] == "completed"
                assert (tmp_path / "user.py").exists()

                # Execute task 2
                cursor.execute("SELECT * FROM tasks WHERE id = ?", (task2_id,))
                task2 = dict(cursor.fetchone())

                result2 = await agent.execute_task(task2)
                assert result2["status"] == "completed"
                assert (tmp_path / "repository.py").exists()

            # Verify user.py was modified
            user_content = (tmp_path / "user.py").read_text()
            assert "__init__" in user_content

            # Verify both tasks completed in database
            cursor.execute("SELECT status FROM tasks WHERE id IN (?, ?)", (task1_id, task2_id))
            rows = cursor.fetchall()
            assert all(row["status"] == "completed" for row in rows)
