"""
Tests for TestWorkerAgent auto-commit integration (T068).

Tests that the test worker agent automatically commits changes after task completion.
"""

import pytest
from unittest.mock import Mock

from codeframe.agents.test_worker_agent import TestWorkerAgent
from codeframe.core.models import AgentMaturity


@pytest.fixture
def mock_db():
    """Mock database instance."""
    db = Mock()
    db.create_blocker = Mock(return_value=1)
    db.update_task_commit_sha = Mock()
    return db


@pytest.fixture
def mock_git_workflow():
    """Mock GitWorkflowManager."""
    git = Mock()
    git.commit_task_changes = Mock(return_value="789abcdef123")
    return git


@pytest.fixture
def test_agent(mock_db, tmp_path):
    """Create TestWorkerAgent with mocks."""
    agent = TestWorkerAgent(
        agent_id="test-001",
        provider="anthropic",
        maturity=AgentMaturity.D1,
        db=mock_db,
        max_correction_attempts=1,  # Speed up tests
    )
    agent.project_root = tmp_path
    agent.tests_dir = tmp_path / "tests"
    agent.tests_dir.mkdir(parents=True, exist_ok=True)

    return agent


@pytest.mark.asyncio
async def test_test_worker_commits_after_successful_task(
    test_agent, mock_db, mock_git_workflow, tmp_path
):
    """
    T068: Test that TestWorkerAgent calls commit_task_changes() after successful task execution.

    This test should FAIL initially because the implementation doesn't exist yet.
    """
    # Arrange
    test_agent.git_workflow = mock_git_workflow

    task = {
        "id": 20,
        "project_id": 1,
        "issue_id": 1,
        "task_number": "cf-3.4.1",
        "parent_issue_number": "cf-3",
        "title": "Generate tests for auth module",
        "description": '{"test_name": "test_auth", "target_file": "auth.py"}',
        "status": "pending",
        "assigned_to": "test-001",
        "depends_on": None,
        "can_parallelize": True,
        "priority": 1,
        "workflow_step": 8,
        "requires_mcp": False,
        "estimated_tokens": 3000,
        "actual_tokens": 0,
        "created_at": "2025-01-01T00:00:00",
        "completed_at": None,
    }

    # Mock test execution to pass immediately
    def mock_execute_tests(test_file):
        return True, "1 passed", {"passed": 1, "failed": 0, "errors": 0, "total": 1}

    # Mock linting to pass without errors
    async def mock_lint(task, test_file, project_id):
        pass  # No-op, doesn't raise

    test_agent._execute_tests = mock_execute_tests
    test_agent._run_and_check_linting = mock_lint
    test_agent.client = None  # Use fallback template

    # Act
    result = await test_agent.execute_task(task, project_id=1)

    # Assert
    assert result["status"] == "completed", "Task should complete successfully"

    # CRITICAL: Verify git commit was called
    mock_git_workflow.commit_task_changes.assert_called_once()
    call_args = mock_git_workflow.commit_task_changes.call_args

    # Verify task parameter (now converted to dict in implementation)
    task_arg = call_args.kwargs.get("task") if call_args.kwargs else call_args.args[0]
    assert task_arg["task_number"] == "cf-3.4.1"

    # Verify files_modified contains test file
    files_arg = call_args.kwargs.get("files_modified") if call_args.kwargs else call_args.args[1]
    assert any("test_auth.py" in f for f in files_arg), "Test file should be in modified files"

    # Verify agent_id
    agent_id_arg = call_args.kwargs.get("agent_id") if call_args.kwargs else call_args.args[2]
    assert agent_id_arg == "test-001"

    # CRITICAL: Verify commit SHA was recorded
    mock_db.update_task_commit_sha.assert_called_once_with(20, "789abcdef123")


@pytest.mark.asyncio
async def test_test_worker_commits_even_after_test_correction(
    test_agent, mock_db, mock_git_workflow
):
    """
    Test that commit happens even after self-correction attempts.
    """
    # Arrange
    test_agent.git_workflow = mock_git_workflow
    test_agent.max_correction_attempts = 2

    task = {
        "id": 21,
        "project_id": 1,
        "issue_id": 1,
        "task_number": "cf-3.4.2",
        "parent_issue_number": "cf-3",
        "title": "Generate tests with correction",
        "description": '{"test_name": "test_complex", "target_file": "complex.py"}',
        "status": "pending",
        "assigned_to": "test-001",
        "depends_on": None,
        "can_parallelize": True,
        "priority": 1,
        "workflow_step": 8,
        "requires_mcp": False,
        "estimated_tokens": 3000,
        "actual_tokens": 0,
        "created_at": "2025-01-01T00:00:00",
        "completed_at": None,
    }

    # Mock tests to fail first, then pass
    attempt_count = 0

    def mock_execute_tests_with_retry(test_file):
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count == 1:
            return False, "1 failed", {"passed": 0, "failed": 1, "errors": 0, "total": 1}
        else:
            return True, "1 passed", {"passed": 1, "failed": 0, "errors": 0, "total": 1}

    test_agent._execute_tests = mock_execute_tests_with_retry
    test_agent.client = None

    # Mock linting to pass without errors
    async def mock_lint(task, test_file, project_id):
        pass  # No-op, doesn't raise

    test_agent._run_and_check_linting = mock_lint

    # Mock correction to return fixed code
    async def mock_correct(orig, error, spec, analysis):
        return "# corrected test code"

    test_agent._correct_failing_tests = mock_correct

    # Act
    result = await test_agent.execute_task(task, project_id=1)

    # Assert
    assert result["status"] == "completed", "Task should complete after correction"

    # CRITICAL: Verify git commit was called
    mock_git_workflow.commit_task_changes.assert_called_once()
    mock_db.update_task_commit_sha.assert_called_once_with(21, "789abcdef123")
