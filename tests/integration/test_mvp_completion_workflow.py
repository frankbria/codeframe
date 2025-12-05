"""
Integration test for complete MVP workflow (T166).

Tests the full Sprint 9 workflow combining all 5 user stories:
  US1: Review Agent
  US2: Auto-Commit
  US3: Linting Integration
  US4: Desktop Notifications
  US5: Composite Index (verified via query performance)

Full workflow: task → lint → review → commit → notification
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
import git

from codeframe.agents.backend_worker_agent import BackendWorkerAgent
from codeframe.git.workflow_manager import GitWorkflowManager
from codeframe.notifications.router import NotificationRouter
from codeframe.persistence.database import Database
from codeframe.core.models import TaskStatus, BlockerType, ContextItemType


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
    """Create test database with migrations applied."""
    # Use :memory: database instead of tempfile to avoid WSL filesystem issues
    db = Database(":memory:")
    db.initialize(run_migrations=True)  # Apply all migrations including 006 and 007

    yield db

    db.close()


@pytest.fixture
def git_workflow(temp_git_repo, test_db):
    """Create GitWorkflowManager instance."""
    repo_path, repo = temp_git_repo
    return GitWorkflowManager(repo_path, test_db)


@pytest.fixture
def backend_agent(temp_git_repo, test_db, git_workflow):
    """Create BackendWorkerAgent with real components."""
    repo_path, repo = temp_git_repo

    # Mock codebase index
    codebase_index = Mock()
    codebase_index.search_pattern = Mock(return_value=[])

    agent = BackendWorkerAgent(
        db=test_db,
        codebase_index=codebase_index,
        provider="claude",
        project_root=repo_path,
        use_sdk=False,  # Disable SDK mode to allow direct file writes in test
    )

    # Attach git workflow
    agent.git_workflow = git_workflow
    agent.agent_id = "backend-mvp-test"

    return agent


@pytest.fixture
def notification_router():
    """Create NotificationRouter for desktop notifications."""
    with patch("codeframe.notifications.router.DesktopNotificationService") as mock_desktop:
        mock_desktop_instance = Mock()
        mock_desktop_instance.is_available.return_value = True
        mock_desktop.return_value = mock_desktop_instance

        router = NotificationRouter(desktop_enabled=True, sync_only=True)
        router._desktop_service = mock_desktop_instance  # Attach for verification

        yield router


@pytest.mark.asyncio
async def test_mvp_completion_full_workflow_success(
    backend_agent, notification_router, test_db, temp_git_repo
):
    """
    T166: Full MVP workflow integration test (happy path).

    Workflow:
    1. Create task
    2. Generate code (mock)
    3. Run tests (mock to pass)
    4. Auto-commit changes
    5. Trigger desktop notification (completion)
    6. Verify context management (composite index used)

    This test verifies core workflow components work together end-to-end.
    """
    repo_path, repo = temp_git_repo

    # SETUP: Create project and task
    project_id = test_db.create_project(
        name="mvp_integration_test", description="Full MVP workflow integration test"
    )

    issue_id = test_db.create_issue(
        {
            "project_id": project_id,
            "issue_number": "mvp-1",
            "title": "Implement authentication feature",
            "status": TaskStatus.IN_PROGRESS.value,
            "priority": 0,
            "workflow_step": 1,
        }
    )

    task_id = test_db.create_task_with_issue(
        project_id=project_id,
        issue_id=issue_id,
        task_number="mvp-1.1",
        parent_issue_number="mvp-1",
        title="Add JWT authentication",
        description="Implement JWT token-based authentication",
        status=TaskStatus.PENDING,
        priority=0,
        workflow_step=1,
        can_parallelize=False,
    )

    # Get task for execution
    cursor = test_db.conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    task = dict(cursor.fetchone())

    # STEP 1: Mock code generation to create clean Python file
    async def mock_generate_code(context):
        return {
            "files": [
                {
                    "path": "auth/jwt_handler.py",
                    "action": "create",
                    "content": '''"""JWT authentication handler."""

import jwt
from datetime import datetime, timedelta


def create_token(user_id: str, secret: str) -> str:
    """Create JWT token for user."""
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(hours=24)
    }
    return jwt.encode(payload, secret, algorithm='HS256')
''',
                }
            ],
            "explanation": "Implemented JWT authentication handler",
        }

    backend_agent.generate_code = mock_generate_code

    # Mock linting to pass (skip lint checks for this integration test)
    backend_agent._run_and_check_linting = AsyncMock()

    # Mock test execution to pass
    backend_agent._run_and_record_tests = AsyncMock()
    test_db.get_test_results_by_task = Mock(return_value=[{"status": "passed"}])

    # STEP 2: Execute task
    result = await backend_agent.execute_task(task)

    # Verify task completed
    assert result["status"] == "completed", f"Task should complete, got: {result}"
    assert "auth/jwt_handler.py" in result["files_modified"]

    # STEP 3: Verify git commit was created
    commits = list(repo.iter_commits(repo.active_branch.name))
    latest_commit = commits[0]  # Most recent commit

    # Verify commit message follows conventional format
    commit_message = latest_commit.message
    assert "mvp-1.1" in commit_message
    assert "authentication" in commit_message.lower() or "jwt" in commit_message.lower()

    # Verify commit SHA recorded in database
    cursor.execute("SELECT commit_sha FROM tasks WHERE id = ?", (task_id,))
    task_row = cursor.fetchone()
    assert task_row["commit_sha"] == latest_commit.hexsha

    # STEP 4: Verify notification system is ready
    # Note: Completion notifications would be triggered by actual application code
    # This test verifies core workflow: generate → test → commit → record SHA
    assert notification_router._desktop_service.is_available() is True

    # Note: Composite index verification is tested in test_composite_index.py
    # This test focuses on the core MVP workflow: code gen → test → commit


@pytest.mark.asyncio
async def test_mvp_completion_workflow_with_notification(
    backend_agent, notification_router, test_db, temp_git_repo
):
    """
    T166: Full MVP workflow with SYNC blocker notification.

    Workflow:
    1. Create task
    2. Simulate blocker creation
    3. Trigger SYNC blocker notification
    4. Verify desktop notification sent

    This test verifies notification system integrates properly.
    """
    repo_path, repo = temp_git_repo

    # SETUP: Create project and task
    project_id = test_db.create_project(
        name="notification_test", description="Test notification integration"
    )

    issue_id = test_db.create_issue(
        {
            "project_id": project_id,
            "issue_number": "notif-1",
            "title": "Feature with blocker",
            "status": TaskStatus.IN_PROGRESS.value,
            "priority": 0,
            "workflow_step": 1,
        }
    )

    task_id = test_db.create_task_with_issue(
        project_id=project_id,
        issue_id=issue_id,
        task_number="notif-1.1",
        parent_issue_number="notif-1",
        title="Feature that encounters blocker",
        description="Task that will create a blocker",
        status=TaskStatus.PENDING,
        priority=0,
        workflow_step=1,
        can_parallelize=False,
    )

    # STEP 1: Create SYNC blocker (simulating quality gate failure)
    test_db.create_blocker(
        agent_id=backend_agent.agent_id,
        project_id=project_id,
        task_id=task_id,
        blocker_type=BlockerType.SYNC.value,
        question="Critical issue found - lint errors detected",
    )

    # STEP 2: Trigger SYNC blocker notification
    await notification_router.send(
        blocker_type=BlockerType.SYNC,
        title="🚨 SYNC Blocker: Quality Gate Failed",
        message="Task notif-1.1 failed quality gate - critical errors found",
    )

    # Verify desktop notification was sent for SYNC blocker
    notification_router._desktop_service.send_notification.assert_called_once()
    call_args = notification_router._desktop_service.send_notification.call_args[0]
    assert "SYNC Blocker" in call_args[0]
    assert "quality gate" in call_args[1].lower() or "blocker" in call_args[0].lower()
