"""
Tests for BackendWorkerAgent auto-commit integration (T066).

Tests that the backend worker agent automatically commits changes after task completion.
"""

import pytest
from unittest.mock import Mock, AsyncMock

from codeframe.agents.backend_worker_agent import BackendWorkerAgent


@pytest.fixture
def mock_db():
    """Mock database instance."""
    db = Mock()
    db.conn = Mock()
    cursor = Mock()
    cursor.fetchone = Mock(return_value=None)
    db.conn.cursor = Mock(return_value=cursor)
    return db


@pytest.fixture
def mock_codebase_index():
    """Mock codebase index."""
    index = Mock()
    index.search_pattern = Mock(return_value=[])
    return index


@pytest.fixture
def mock_git_workflow():
    """Mock GitWorkflowManager."""
    git = Mock()
    git.commit_task_changes = Mock(return_value="abc123def456")
    return git


@pytest.fixture
def backend_agent(mock_db, mock_codebase_index, tmp_path):
    """Create BackendWorkerAgent with mocks."""
    agent = BackendWorkerAgent(
        db=mock_db,
        codebase_index=mock_codebase_index,
        provider="claude",
        project_root=tmp_path,
    )
    return agent


@pytest.mark.asyncio
async def test_backend_worker_commits_after_successful_task(
    backend_agent, mock_db, mock_git_workflow, tmp_path
):
    """
    T066: Test that BackendWorkerAgent calls commit_task_changes() after successful task execution.

    This test should FAIL initially because the implementation doesn't exist yet.
    """
    # Arrange
    backend_agent.git_workflow = mock_git_workflow
    backend_agent.agent_id = "backend-001"

    task = {
        "id": 1,
        "project_id": 1,
        "task_number": "cf-1.5.3",
        "title": "Implement user authentication",
        "description": "Add JWT-based authentication",
        "status": "pending",
        "issue_id": 1,
    }

    # Mock file creation
    (tmp_path / "auth.py").write_text("# authentication code")

    # Mock generate_code to return file changes
    async def mock_generate_code(context):
        return {
            "files": [{"path": "auth.py", "action": "create", "content": "# authentication code"}],
            "explanation": "Implemented authentication",
        }

    backend_agent.generate_code = mock_generate_code
    backend_agent._run_and_record_tests = AsyncMock()

    # Mock test results to pass
    mock_db.get_test_results_by_task = Mock(return_value=[{"status": "passed"}])
    mock_db.update_task_commit_sha = Mock()

    # Act
    result = await backend_agent.execute_task(task)

    # Assert
    assert result["status"] == "completed", "Task should complete successfully"

    # CRITICAL: Verify git commit was called
    mock_git_workflow.commit_task_changes.assert_called_once()
    call_args = mock_git_workflow.commit_task_changes.call_args

    # Handle both positional and keyword arguments
    if call_args.kwargs:
        # Keyword arguments used
        assert call_args.kwargs["task"] == task
        assert "auth.py" in call_args.kwargs["files_modified"]
        assert call_args.kwargs["agent_id"] == "backend-001"
    else:
        # Positional arguments used
        assert call_args.args[0] == task
        assert "auth.py" in call_args.args[1]
        assert call_args.args[2] == "backend-001"

    # CRITICAL: Verify commit SHA was recorded in database
    mock_db.update_task_commit_sha.assert_called_once_with(1, "abc123def456")


@pytest.mark.asyncio
async def test_backend_worker_no_commit_on_failure(backend_agent, mock_db, mock_git_workflow):
    """
    Test that no commit is made when task execution fails.
    """
    # Arrange
    backend_agent.git_workflow = mock_git_workflow
    backend_agent.agent_id = "backend-001"

    task = {
        "id": 2,
        "project_id": 1,
        "task_number": "cf-1.5.4",
        "title": "Broken task",
        "description": "This will fail",
        "status": "pending",
        "issue_id": 1,
    }

    # Mock generate_code to raise exception
    async def mock_generate_code_fail(context):
        raise RuntimeError("Code generation failed")

    backend_agent.generate_code = mock_generate_code_fail

    # Act
    result = await backend_agent.execute_task(task)

    # Assert
    assert result["status"] == "failed"

    # CRITICAL: Verify NO commit was made
    mock_git_workflow.commit_task_changes.assert_not_called()


@pytest.mark.asyncio
async def test_backend_worker_graceful_commit_failure(
    backend_agent, mock_db, mock_git_workflow, tmp_path
):
    """
    T073: Test that commit failures don't block task completion (graceful degradation).
    """
    # Arrange
    backend_agent.git_workflow = mock_git_workflow
    backend_agent.agent_id = "backend-001"

    # Make commit fail
    mock_git_workflow.commit_task_changes.side_effect = Exception("Git error")

    task = {
        "id": 3,
        "project_id": 1,
        "task_number": "cf-1.5.5",
        "title": "Task with git issue",
        "description": "Commit will fail but task should succeed",
        "status": "pending",
        "issue_id": 1,
    }

    (tmp_path / "feature.py").write_text("# code")

    async def mock_generate_code(context):
        return {
            "files": [{"path": "feature.py", "action": "create", "content": "# code"}],
            "explanation": "Added feature",
        }

    backend_agent.generate_code = mock_generate_code
    backend_agent._run_and_record_tests = AsyncMock()
    mock_db.get_test_results_by_task = Mock(return_value=[{"status": "passed"}])

    # Act - should NOT raise exception
    result = await backend_agent.execute_task(task)

    # Assert
    assert result["status"] == "completed", "Task should still complete despite commit failure"
    mock_git_workflow.commit_task_changes.assert_called_once()
