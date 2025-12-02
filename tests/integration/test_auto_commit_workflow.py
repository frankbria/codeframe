"""
Integration test for auto-commit workflow (T074).

Tests the full workflow: task completion → auto-commit → SHA recorded in database.
This integration test verifies that all components work together correctly.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock
import git

from codeframe.agents.backend_worker_agent import BackendWorkerAgent
from codeframe.git.workflow_manager import GitWorkflowManager
from codeframe.persistence.database import Database
from codeframe.core.models import TaskStatus


@pytest.fixture
def temp_git_repo():
    """Create a temporary git repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Initialize git repo
        repo = git.Repo.init(repo_path, initial_branch="main")

        # Configure git user (required for commits)
        repo.config_writer().set_value("user", "name", "Test User").release()
        repo.config_writer().set_value("user", "email", "test@example.com").release()

        # Create initial commit
        readme = repo_path / "README.md"
        readme.write_text("# Test Project\n")
        repo.index.add(["README.md"])
        repo.index.commit("Initial commit")

        yield repo_path, repo


@pytest.fixture
def test_db():
    """Create test database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    db = Database(db_path)
    db.initialize()

    yield db

    db.close()
    db_path.unlink()


@pytest.fixture
def git_workflow(temp_git_repo, test_db):
    """Create GitWorkflowManager instance."""
    repo_path, repo = temp_git_repo
    return GitWorkflowManager(repo_path, test_db)


@pytest.fixture
def backend_agent(temp_git_repo, test_db, git_workflow):
    """Create BackendWorkerAgent with real git workflow."""
    repo_path, repo = temp_git_repo

    # Mock codebase index
    codebase_index = Mock()
    codebase_index.search_pattern = Mock(return_value=[])

    agent = BackendWorkerAgent(
        project_id=1,
        db=test_db,
        codebase_index=codebase_index,
        provider="claude",
        project_root=repo_path,
        use_sdk=False,
    )

    # Attach git workflow
    agent.git_workflow = git_workflow
    agent.agent_id = "backend-integration-test"

    return agent


@pytest.mark.asyncio
async def test_full_auto_commit_workflow(backend_agent, test_db, temp_git_repo):
    """
    T074: Integration test for complete auto-commit workflow.

    Verifies:
    1. Task execution completes successfully
    2. Git commit is created with conventional message
    3. Commit SHA is recorded in database
    4. Task can be retrieved by commit SHA

    This test should FAIL initially because the integration doesn't exist yet.
    """
    repo_path, repo = temp_git_repo

    # Create project
    project_id = test_db.create_project(
        name="integration_test", description="Integration test for auto-commit"
    )

    # Create issue
    issue_id = test_db.create_issue(
        {
            "project_id": project_id,
            "issue_number": "int-1",
            "title": "Integration Test Issue",
            "status": TaskStatus.IN_PROGRESS.value,
            "priority": 0,
            "workflow_step": 1,
        }
    )

    # Create task
    task_id = test_db.create_task_with_issue(
        project_id=project_id,
        issue_id=issue_id,
        task_number="int-1.1",
        parent_issue_number="int-1",
        title="Add integration test feature",
        description="Implement auto-commit integration testing",
        status=TaskStatus.PENDING,
        priority=0,
        workflow_step=1,
        can_parallelize=False,
    )

    # Get task for execution
    cursor = test_db.conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    task = dict(cursor.fetchone())

    # Mock code generation to create a real file
    async def mock_generate_code(context):
        return {
            "files": [
                {
                    "path": "integration_feature.py",
                    "action": "create",
                    "content": "# Auto-commit integration feature\n\ndef test_feature():\n    return True\n",
                }
            ],
            "explanation": "Implemented integration test feature",
        }

    backend_agent.generate_code = mock_generate_code

    # Mock test execution to pass
    backend_agent._run_and_record_tests = AsyncMock()
    test_db.get_test_results_by_task = Mock(return_value=[{"status": "passed"}])

    # STEP 1: Execute task
    result = await backend_agent.execute_task(task)

    # Assert task completed
    assert result["status"] == "completed", f"Task should complete, got: {result}"
    assert "integration_feature.py" in result["files_modified"]

    # STEP 2: Verify git commit was created
    commits = list(repo.iter_commits(repo.active_branch.name))
    latest_commit = commits[0]  # Most recent commit

    # Verify commit message follows conventional format
    commit_message = latest_commit.message
    assert (
        commit_message.startswith("feat(int-1.1): Add integration test feature")
        or commit_message.startswith("chore(int-1.1): Add integration test feature")
        or commit_message.startswith("test(int-1.1): Add integration test feature")
    ), f"Unexpected commit message: {commit_message}"
    assert "Implement auto-commit integration testing" in commit_message
    assert "Modified files:" in commit_message
    assert "integration_feature.py" in commit_message

    # STEP 3: Verify commit SHA was recorded in database
    cursor.execute("SELECT commit_sha FROM tasks WHERE id = ?", (task_id,))
    task_row = cursor.fetchone()

    assert task_row is not None
    assert task_row["commit_sha"] is not None
    assert task_row["commit_sha"] == latest_commit.hexsha

    # STEP 4: Verify task can be retrieved by commit SHA
    retrieved_task = test_db.get_task_by_commit(latest_commit.hexsha)

    assert retrieved_task is not None
    assert retrieved_task["id"] == task_id
    assert retrieved_task["task_number"] == "int-1.1"
    assert retrieved_task["commit_sha"] == latest_commit.hexsha

    # STEP 5: Verify retrieval by short SHA also works
    short_sha = latest_commit.hexsha[:7]
    retrieved_by_short = test_db.get_task_by_commit(short_sha)

    assert retrieved_by_short is not None
    assert retrieved_by_short["id"] == task_id


@pytest.mark.asyncio
async def test_auto_commit_with_multiple_files(backend_agent, test_db, temp_git_repo):
    """
    Integration test with multiple file modifications.
    """
    repo_path, repo = temp_git_repo

    # Create project and task
    project_id = test_db.create_project(
        name="multi_file_test", description="Test multiple file commits"
    )

    issue_id = test_db.create_issue(
        {
            "project_id": project_id,
            "issue_number": "mf-1",
            "title": "Multi-file Test",
            "status": TaskStatus.IN_PROGRESS.value,
            "priority": 0,
            "workflow_step": 1,
        }
    )

    task_id = test_db.create_task_with_issue(
        project_id=project_id,
        issue_id=issue_id,
        task_number="mf-1.1",
        parent_issue_number="mf-1",
        title="Refactor authentication module",
        description="Split auth into separate files",
        status=TaskStatus.PENDING,
        priority=0,
        workflow_step=1,
        can_parallelize=False,
    )

    cursor = test_db.conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    task = dict(cursor.fetchone())

    # Mock multiple file creation
    async def mock_generate_code(context):
        return {
            "files": [
                {"path": "auth/handler.py", "action": "create", "content": "# Auth handler\n"},
                {"path": "auth/validator.py", "action": "create", "content": "# Validator\n"},
                {"path": "auth/__init__.py", "action": "create", "content": "# Package init\n"},
            ],
            "explanation": "Refactored authentication into modular structure",
        }

    backend_agent.generate_code = mock_generate_code
    backend_agent._run_and_record_tests = AsyncMock()
    test_db.get_test_results_by_task = Mock(return_value=[{"status": "passed"}])

    # Execute task
    result = await backend_agent.execute_task(task)

    assert result["status"] == "completed"
    assert len(result["files_modified"]) == 3

    # Verify commit includes all files
    latest_commit = list(repo.iter_commits(repo.active_branch.name))[0]
    commit_message = latest_commit.message

    assert "auth/handler.py" in commit_message
    assert "auth/validator.py" in commit_message
    assert "auth/__init__.py" in commit_message

    # Verify commit SHA recorded
    cursor.execute("SELECT commit_sha FROM tasks WHERE id = ?", (task_id,))
    task_row = cursor.fetchone()
    assert task_row["commit_sha"] == latest_commit.hexsha


@pytest.mark.asyncio
async def test_no_commit_when_task_fails(backend_agent, test_db, temp_git_repo):
    """
    Integration test verifying NO commit when task execution fails.
    """
    repo_path, repo = temp_git_repo

    # Get initial commit count
    initial_commit_count = len(list(repo.iter_commits(repo.active_branch.name)))

    # Create project and task
    project_id = test_db.create_project(name="failure_test", description="Test failed task")

    issue_id = test_db.create_issue(
        {
            "project_id": project_id,
            "issue_number": "fail-1",
            "title": "Failure Test",
            "status": TaskStatus.IN_PROGRESS.value,
            "priority": 0,
            "workflow_step": 1,
        }
    )

    task_id = test_db.create_task_with_issue(
        project_id=project_id,
        issue_id=issue_id,
        task_number="fail-1.1",
        parent_issue_number="fail-1",
        title="Task that will fail",
        description="This task will raise an exception",
        status=TaskStatus.PENDING,
        priority=0,
        workflow_step=1,
        can_parallelize=False,
    )

    cursor = test_db.conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    task = dict(cursor.fetchone())

    # Mock code generation to fail
    async def mock_generate_code_fail(context):
        raise RuntimeError("Intentional failure for testing")

    backend_agent.generate_code = mock_generate_code_fail

    # Execute task (should fail)
    result = await backend_agent.execute_task(task)

    assert result["status"] == "failed"

    # Verify NO new commit was created
    final_commit_count = len(list(repo.iter_commits(repo.active_branch.name)))
    assert final_commit_count == initial_commit_count, "No commit should be created on failure"

    # Verify commit_sha is NULL in database
    cursor.execute("SELECT commit_sha FROM tasks WHERE id = ?", (task_id,))
    task_row = cursor.fetchone()
    assert task_row["commit_sha"] is None
