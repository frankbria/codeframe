"""
Tests for worker agent task dictionary interface standardization.

This test module verifies that:
1. LeadAgent passes complete task dictionaries to worker agents (using task.to_dict())
2. FrontendWorkerAgent accepts task dictionaries (not Task objects)
3. TestWorkerAgent accepts task dictionaries (not Task objects)

This standardizes on dictionary input to match BackendWorkerAgent and ReviewWorkerAgent.

Issue: Interface mismatch between LeadAgent and worker agents - minimal dict with only
id/title/description was being passed, missing fields like project_id, task_number.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path

from codeframe.core.models import Task, TaskStatus


class TestLeadAgentTaskDictCreation:
    """Tests for LeadAgent creating complete task dictionaries."""

    @pytest.mark.asyncio
    async def test_assign_and_execute_task_passes_complete_task_dict(
        self, tmp_path: Path
    ):
        """Test that _assign_and_execute_task passes complete task dict to agents.

        The task dict should include all fields from Task.to_dict(), not just
        id/title/description.
        """
        from codeframe.agents.lead_agent import LeadAgent
        from codeframe.persistence.database import Database

        # Setup database
        db = Database(":memory:")
        db.initialize()

        project_id = db.create_project(
            name="dict-test-project",
            description="Test task dict creation",
            source_type="empty",
            workspace_path=str(tmp_path),
        )

        issue_id = db.create_issue({
            "project_id": project_id,
            "issue_number": "TD-001",
            "title": "Test Issue",
            "description": "Test issue",
            "priority": 1,
            "workflow_step": 1,
        })

        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="TD-001-1",
            parent_issue_number="TD-001",
            title="Test Task",
            description="Test task description",
            status=TaskStatus.PENDING,
            priority=2,
            workflow_step=5,
            can_parallelize=False,
        )

        # Create LeadAgent with mocked pool
        with patch("codeframe.agents.lead_agent.AgentPoolManager") as mock_pool_class:
            mock_pool = Mock()
            mock_pool.get_or_create_agent.return_value = "backend-001"
            mock_pool.mark_agent_busy.return_value = None
            mock_pool.mark_agent_idle.return_value = None

            # Capture the task dict passed to execute_task
            captured_task_dict = None

            async def capture_execute_task(task_dict):
                nonlocal captured_task_dict
                captured_task_dict = task_dict
                return {"status": "completed"}

            mock_agent = Mock()
            mock_agent.execute_task = capture_execute_task
            mock_pool.get_agent_instance.return_value = mock_agent
            mock_pool_class.return_value = mock_pool

            lead_agent = LeadAgent(
                project_id=project_id,
                db=db,
                api_key="sk-ant-test-key",
                ws_manager=None,
            )
            lead_agent.agent_pool_manager = mock_pool

            # Mock review agent
            with patch.object(lead_agent.agent_pool_manager, "get_or_create_agent") as mock_get:
                mock_get.side_effect = ["backend-001", "review-001"]

                mock_review = Mock()
                mock_review_report = Mock()
                mock_review_report.status = "approved"
                mock_review_report.overall_score = 9.0
                mock_review.execute_task = AsyncMock(return_value=mock_review_report)

                def get_instance(agent_id):
                    if "review" in agent_id:
                        return mock_review
                    return mock_agent

                mock_pool.get_agent_instance.side_effect = get_instance

                task = db.get_task(task_id)
                await lead_agent._assign_and_execute_task(task, {})

        # CRITICAL: Verify all required fields are present
        assert captured_task_dict is not None, "execute_task was not called"

        # Core fields that must be present
        assert "id" in captured_task_dict
        assert "project_id" in captured_task_dict, \
            "project_id missing from task dict (needed for git workflow)"
        assert "task_number" in captured_task_dict, \
            "task_number missing from task dict (needed for git workflow)"
        assert "title" in captured_task_dict
        assert "description" in captured_task_dict

        # Additional fields from to_dict()
        assert "issue_id" in captured_task_dict
        assert "parent_issue_number" in captured_task_dict
        assert "status" in captured_task_dict
        assert "priority" in captured_task_dict
        assert "workflow_step" in captured_task_dict

        # Verify values
        assert captured_task_dict["id"] == task_id
        assert captured_task_dict["project_id"] == project_id
        assert captured_task_dict["task_number"] == "TD-001-1"


class TestFrontendWorkerAgentDictInterface:
    """Tests for FrontendWorkerAgent accepting dictionary input."""

    @pytest.fixture
    def temp_web_ui_dir(self, tmp_path):
        """Create temporary web-ui directory structure."""
        web_ui = tmp_path / "web-ui"
        components_dir = web_ui / "src" / "components"
        components_dir.mkdir(parents=True)
        return web_ui

    @pytest.fixture
    def frontend_agent(self, temp_web_ui_dir):
        """Create FrontendWorkerAgent for testing."""
        from codeframe.agents.frontend_worker_agent import FrontendWorkerAgent

        agent = FrontendWorkerAgent(
            agent_id="frontend-dict-test-001",
            provider="anthropic",
            api_key="test-key",
        )
        agent.web_ui_root = temp_web_ui_dir
        agent.components_dir = temp_web_ui_dir / "src" / "components"
        return agent

    @pytest.mark.asyncio
    async def test_execute_task_accepts_dict_input(self, frontend_agent):
        """Test that execute_task accepts a dictionary instead of Task object."""
        # Create task as dictionary (matching what LeadAgent will pass)
        task_dict = {
            "id": 42,
            "project_id": 1,
            "issue_id": 10,
            "task_number": "FE-001-1",
            "parent_issue_number": "FE-001",
            "title": "Create TestComponent",
            "description": '{"name": "TestComponent", "description": "A test component"}',
            "status": "pending",
            "assigned_to": None,
            "depends_on": "",
            "can_parallelize": False,
            "priority": 2,
            "workflow_step": 5,
            "requires_mcp": False,
            "estimated_tokens": 0,
            "actual_tokens": None,
        }

        # Mock the Claude API call
        with patch.object(frontend_agent, "_generate_react_component") as mock_gen:
            mock_gen.return_value = "export const TestComponent = () => <div>Test</div>"

            # This should not raise AttributeError for task.id, task.title, etc.
            result = await frontend_agent.execute_task(task_dict)

        assert result["status"] in ("completed", "failed")

    @pytest.mark.asyncio
    async def test_execute_task_dict_access_patterns(self, frontend_agent):
        """Test that all dictionary access patterns work correctly."""
        task_dict = {
            "id": 99,
            "project_id": 5,
            "issue_id": 20,
            "task_number": "FE-002-1",
            "parent_issue_number": "FE-002",
            "title": "Create Another Component",
            "description": '{"name": "Another", "description": "Another component"}',
            "status": "pending",
            "assigned_to": None,
            "depends_on": "",
            "can_parallelize": False,
            "priority": 1,
            "workflow_step": 3,
            "requires_mcp": False,
            "estimated_tokens": 1000,
            "actual_tokens": None,
        }

        with patch.object(frontend_agent, "_generate_react_component") as mock_gen:
            mock_gen.return_value = "export const Another = () => <div>Another</div>"

            # The method should access task["id"], task["title"], etc.
            # instead of task.id, task.title (which would fail for dict)
            result = await frontend_agent.execute_task(task_dict)

        # Verify no AttributeError occurred
        assert "status" in result


class TestTestWorkerAgentDictInterface:
    """Tests for TestWorkerAgent accepting dictionary input."""

    @pytest.fixture
    def temp_tests_dir(self, tmp_path):
        """Create temporary tests directory."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        return tests_dir

    @pytest.fixture
    def test_agent(self, temp_tests_dir):
        """Create TestWorkerAgent for testing."""
        from codeframe.agents.test_worker_agent import TestWorkerAgent

        agent = TestWorkerAgent(
            agent_id="test-dict-test-001",
            provider="anthropic",
            api_key="test-key",
        )
        agent.tests_dir = temp_tests_dir
        agent.project_root = temp_tests_dir.parent
        return agent

    @pytest.mark.asyncio
    async def test_execute_task_accepts_dict_input(self, test_agent):
        """Test that execute_task accepts a dictionary instead of Task object."""
        # Create task as dictionary (matching what LeadAgent will pass)
        task_dict = {
            "id": 55,
            "project_id": 2,
            "issue_id": 15,
            "task_number": "TE-001-1",
            "parent_issue_number": "TE-001",
            "title": "Create tests for UserService",
            "description": '{"test_name": "test_user", "target_file": "services/user.py"}',
            "status": "pending",
            "assigned_to": None,
            "depends_on": "",
            "can_parallelize": False,
            "priority": 2,
            "workflow_step": 7,
            "requires_mcp": False,
            "estimated_tokens": 500,
            "actual_tokens": None,
        }

        # Mock the Claude API call and test execution
        with patch.object(test_agent, "_generate_pytest_tests") as mock_gen:
            mock_gen.return_value = "def test_user(): pass"

            with patch.object(test_agent, "_execute_and_correct_tests") as mock_exec:
                mock_exec.return_value = {
                    "passed": True,
                    "passed_count": 1,
                    "total_count": 1,
                }

                # This should not raise AttributeError for task.id, etc.
                result = await test_agent.execute_task(task_dict)

        assert result["status"] in ("completed", "failed")

    @pytest.mark.asyncio
    async def test_execute_task_dict_access_patterns(self, test_agent):
        """Test that all dictionary access patterns work correctly."""
        task_dict = {
            "id": 77,
            "project_id": 3,
            "issue_id": 25,
            "task_number": "TE-002-1",
            "parent_issue_number": "TE-002",
            "title": "Create tests for AuthService",
            "description": '{"test_name": "test_auth", "target_file": "services/auth.py"}',
            "status": "pending",
            "assigned_to": None,
            "depends_on": "",
            "can_parallelize": False,
            "priority": 1,
            "workflow_step": 7,
            "requires_mcp": False,
            "estimated_tokens": 800,
            "actual_tokens": None,
        }

        with patch.object(test_agent, "_generate_pytest_tests") as mock_gen:
            mock_gen.return_value = "def test_auth(): pass"

            with patch.object(test_agent, "_execute_and_correct_tests") as mock_exec:
                mock_exec.return_value = {
                    "passed": True,
                    "passed_count": 1,
                    "total_count": 1,
                }

                result = await test_agent.execute_task(task_dict)

        # Verify no AttributeError occurred
        assert "status" in result


class TestTaskToDictMethod:
    """Tests to verify Task.to_dict() produces the expected format."""

    def test_task_to_dict_includes_all_required_fields(self):
        """Verify Task.to_dict() includes all fields needed by worker agents."""
        task = Task(
            id=1,
            project_id=10,
            issue_id=5,
            task_number="T-001",
            parent_issue_number="I-001",
            title="Test Task",
            description="Test description",
            status=TaskStatus.PENDING,
            assigned_to="agent-001",
            depends_on="T-000",
            can_parallelize=True,
            priority=2,
            workflow_step=3,
            requires_mcp=True,
            estimated_tokens=500,
            actual_tokens=100,
        )

        task_dict = task.to_dict()

        # All worker agents need these fields
        assert task_dict["id"] == 1
        assert task_dict["project_id"] == 10
        assert task_dict["issue_id"] == 5
        assert task_dict["task_number"] == "T-001"
        assert task_dict["parent_issue_number"] == "I-001"
        assert task_dict["title"] == "Test Task"
        assert task_dict["description"] == "Test description"
        assert task_dict["status"] == "pending"  # String, not enum
        assert task_dict["assigned_to"] == "agent-001"
        assert task_dict["depends_on"] == "T-000"
        assert task_dict["can_parallelize"] is True
        assert task_dict["priority"] == 2
        assert task_dict["workflow_step"] == 3
        assert task_dict["requires_mcp"] is True
        assert task_dict["estimated_tokens"] == 500
        assert task_dict["actual_tokens"] == 100
