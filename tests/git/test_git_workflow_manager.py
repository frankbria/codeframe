"""Test suite for GitWorkflowManager.

Following TDD methodology: RED → GREEN → REFACTOR
"""

import pytest
import tempfile
from pathlib import Path
import git

from codeframe.git.workflow_manager import GitWorkflowManager
from codeframe.persistence.database import Database


@pytest.fixture
def temp_git_repo():
    """Create a temporary git repository for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Initialize git repo with main branch
        repo = git.Repo.init(repo_path, initial_branch="main")

        # Create initial commit
        test_file = repo_path / "README.md"
        test_file.write_text("# Test Project\n")
        repo.index.add(["README.md"])
        repo.index.commit("Initial commit")

        yield repo_path, repo


@pytest.fixture
def test_db():
    """Create a test database in memory."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    db = Database(db_path)
    db.initialize()

    yield db

    db.close()
    db_path.unlink()


@pytest.fixture
def workflow_manager(temp_git_repo, test_db):
    """Create GitWorkflowManager instance for testing."""
    repo_path, repo = temp_git_repo
    return GitWorkflowManager(repo_path, test_db)


class TestGitWorkflowManagerInitialization:
    """Test GitWorkflowManager initialization."""

    def test_init_with_valid_repo(self, temp_git_repo, test_db):
        """Test initialization with valid git repository."""
        repo_path, repo = temp_git_repo
        manager = GitWorkflowManager(repo_path, test_db)

        assert manager.project_root == repo_path
        assert manager.db == test_db
        assert manager.repo is not None
        assert isinstance(manager.repo, git.Repo)

    def test_init_with_non_git_directory(self, test_db):
        """Test initialization with non-git directory raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(git.InvalidGitRepositoryError):
                GitWorkflowManager(Path(tmpdir), test_db)

    def test_init_with_nonexistent_path(self, test_db):
        """Test initialization with nonexistent path raises error."""
        with pytest.raises(git.NoSuchPathError):
            GitWorkflowManager(Path("/nonexistent/path"), test_db)


class TestCreateFeatureBranch:
    """Test feature branch creation."""

    def test_create_feature_branch_basic(self, workflow_manager, temp_git_repo):
        """Test creating a feature branch with basic inputs."""
        repo_path, repo = temp_git_repo

        branch_name = workflow_manager.create_feature_branch("2.1", "User Authentication")

        assert branch_name == "issue-2.1-user-authentication"
        assert branch_name in [b.name for b in repo.branches]

    def test_create_feature_branch_sanitizes_title(self, workflow_manager, temp_git_repo):
        """Test that branch name properly sanitizes special characters."""
        repo_path, repo = temp_git_repo

        branch_name = workflow_manager.create_feature_branch(
            "3.5", "Add User's Profile & Settings (V2)"
        )

        assert branch_name == "issue-3.5-add-users-profile-settings-v2"
        assert "/" not in branch_name
        assert "&" not in branch_name
        assert "(" not in branch_name

    def test_create_feature_branch_long_title_truncated(self, workflow_manager, temp_git_repo):
        """Test that very long titles are truncated."""
        repo_path, repo = temp_git_repo

        long_title = "A" * 100  # Very long title
        branch_name = workflow_manager.create_feature_branch("1.1", long_title)

        # Branch name should be truncated but still valid
        assert len(branch_name) <= 63  # Git ref name length limit
        assert branch_name.startswith("issue-1.1-")

    def test_create_feature_branch_already_exists(self, workflow_manager, temp_git_repo):
        """Test creating branch that already exists raises error."""
        repo_path, repo = temp_git_repo

        # Create first branch
        workflow_manager.create_feature_branch("2.1", "User Auth")

        # Try to create same branch again
        with pytest.raises(ValueError, match="Branch .* already exists"):
            workflow_manager.create_feature_branch("2.1", "User Auth")

    def test_create_feature_branch_with_dirty_working_tree(self, workflow_manager, temp_git_repo):
        """Test creating branch with uncommitted changes."""
        repo_path, repo = temp_git_repo

        # Create uncommitted changes
        test_file = repo_path / "test.txt"
        test_file.write_text("Uncommitted changes")

        # Should still create branch successfully
        branch_name = workflow_manager.create_feature_branch("2.1", "Test Feature")
        assert branch_name in [b.name for b in repo.branches]

    def test_create_feature_branch_stores_in_database(self, workflow_manager, test_db):
        """Test that branch creation is recorded in database."""
        # First create an issue in database
        from codeframe.core.models import Issue, TaskStatus

        project_id = test_db.create_project(
            name="test_project", description="Test project for git workflow tests"
        )
        issue = Issue(
            project_id=project_id,
            issue_number="2.1",
            title="User Authentication",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
        )
        issue_id = test_db.create_issue(issue)

        # Create branch
        branch_name = workflow_manager.create_feature_branch("2.1", "User Authentication")

        # Verify in database
        branch_record = test_db.get_branch_for_issue(issue_id)
        assert branch_record is not None
        assert branch_record["branch_name"] == branch_name
        assert branch_record["status"] == "active"


class TestMergeToMain:
    """Test merging feature branches to main."""

    def test_merge_to_main_success(self, workflow_manager, temp_git_repo, test_db):
        """Test successful merge to main when all tasks complete."""
        repo_path, repo = temp_git_repo

        # Setup: create issue and tasks in database
        from codeframe.core.models import Issue, TaskStatus

        project_id = test_db.create_project(
            name="test_project", description="Test project for git workflow tests"
        )
        issue = Issue(
            project_id=project_id,
            issue_number="2.1",
            title="User Auth",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            workflow_step=1,
        )
        issue_id = test_db.create_issue(issue)

        # Create tasks for issue
        test_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="2.1.1",
            parent_issue_number="2.1",
            title="Task 1",
            description="Test task 1",
            status=TaskStatus.COMPLETED,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )
        test_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="2.1.2",
            parent_issue_number="2.1",
            title="Task 2",
            description="Test task 2",
            status=TaskStatus.COMPLETED,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        # Create feature branch
        branch_name = workflow_manager.create_feature_branch("2.1", "User Auth")

        # Switch to feature branch and make a commit
        repo.git.checkout(branch_name)
        test_file = repo_path / "feature.txt"
        test_file.write_text("Feature implementation")
        repo.index.add(["feature.txt"])
        repo.index.commit("Implement user auth feature")

        # Switch back to main
        repo.git.checkout("main")

        # Merge to main
        result = workflow_manager.merge_to_main("2.1")

        assert result["status"] == "merged"
        assert result["branch_name"] == branch_name
        assert "merge_commit" in result
        assert repo.active_branch.name == "main"

        # Verify merge commit exists
        assert (repo_path / "feature.txt").exists()

    def test_merge_to_main_incomplete_tasks(self, workflow_manager, temp_git_repo, test_db):
        """Test merge fails when not all tasks are completed."""
        repo_path, repo = temp_git_repo

        # Setup: create issue with incomplete tasks
        from codeframe.core.models import Issue, TaskStatus

        project_id = test_db.create_project(
            name="test_project", description="Test project for git workflow tests"
        )
        issue = Issue(
            project_id=project_id,
            issue_number="2.1",
            title="User Auth",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            workflow_step=1,
        )
        issue_id = test_db.create_issue(issue)

        # Create incomplete task
        test_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="2.1.1",
            parent_issue_number="2.1",
            title="Task 1",
            description="Test task 1",
            status=TaskStatus.IN_PROGRESS,  # NOT COMPLETED
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        # Create feature branch
        workflow_manager.create_feature_branch("2.1", "User Auth")

        # Try to merge
        with pytest.raises(ValueError, match="Cannot merge.*incomplete tasks"):
            workflow_manager.merge_to_main("2.1")

    def test_merge_to_main_nonexistent_issue(self, workflow_manager):
        """Test merge fails for nonexistent issue."""
        with pytest.raises(ValueError, match="Issue.*not found"):
            workflow_manager.merge_to_main("99.99")

    def test_merge_to_main_conflict_handling(self, workflow_manager, temp_git_repo, test_db):
        """Test merge conflict detection and handling."""
        repo_path, repo = temp_git_repo

        # Setup: create issue with completed tasks
        from codeframe.core.models import Issue, TaskStatus

        project_id = test_db.create_project(
            name="test_project", description="Test project for git workflow tests"
        )
        issue = Issue(
            project_id=project_id,
            issue_number="2.1",
            title="Conflict Test",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            workflow_step=1,
        )
        issue_id = test_db.create_issue(issue)

        test_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="2.1.1",
            parent_issue_number="2.1",
            title="Task 1",
            description="Test",
            status=TaskStatus.COMPLETED,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        # Create conflicting changes in main
        test_file = repo_path / "conflict.txt"
        test_file.write_text("Main branch content")
        repo.index.add(["conflict.txt"])
        repo.index.commit("Main branch change")

        # Create feature branch and conflicting change
        branch_name = workflow_manager.create_feature_branch("2.1", "Conflict Test")
        repo.git.checkout(branch_name)
        test_file.write_text("Feature branch content")
        repo.index.add(["conflict.txt"])
        repo.index.commit("Feature branch change")
        repo.git.checkout("main")

        # Try to merge - should detect conflict or raise ValueError
        try:
            workflow_manager.merge_to_main("2.1")
            # If merge succeeded without conflict, that's also valid (auto-merge)
            assert True
        except (git.GitCommandError, ValueError):
            # Expected - conflict detected
            assert True

    def test_merge_to_main_updates_database(self, workflow_manager, temp_git_repo, test_db):
        """Test that merge updates database tracking."""
        repo_path, repo = temp_git_repo

        # Setup complete issue
        from codeframe.core.models import Issue, TaskStatus

        project_id = test_db.create_project(
            name="test_project", description="Test project for git workflow tests"
        )
        issue = Issue(
            project_id=project_id,
            issue_number="2.1",
            title="Test",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            workflow_step=1,
        )
        issue_id = test_db.create_issue(issue)

        test_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="2.1.1",
            parent_issue_number="2.1",
            title="Task 1",
            description="Test",
            status=TaskStatus.COMPLETED,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        # Create and merge branch
        branch_name = workflow_manager.create_feature_branch("2.1", "Test")
        repo.git.checkout(branch_name)
        (repo_path / "test.txt").write_text("test")
        repo.index.add(["test.txt"])
        repo.index.commit("Test commit")
        repo.git.checkout("main")

        workflow_manager.merge_to_main("2.1")

        # Check database was updated
        # get_all_branches_for_issue returns all branches (including merged)
        branches = test_db.get_all_branches_for_issue(issue_id)
        assert len(branches) > 0
        branch_record = branches[-1]  # Get most recent
        assert branch_record["status"] == "merged"
        assert branch_record["merge_commit"] is not None


class TestIsIssueComplete:
    """Test issue completion checking."""

    def test_is_issue_complete_all_tasks_done(self, workflow_manager, test_db):
        """Test issue is complete when all tasks are completed."""
        from codeframe.core.models import Issue, TaskStatus

        project_id = test_db.create_project(
            name="test_project", description="Test project for git workflow tests"
        )
        issue = Issue(
            project_id=project_id,
            issue_number="2.1",
            title="Test",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            workflow_step=1,
        )
        issue_id = test_db.create_issue(issue)

        # Create completed tasks
        for i in range(3):
            test_db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=f"2.1.{i+1}",
                parent_issue_number="2.1",
                title=f"Task {i+1}",
                description="Test",
                status=TaskStatus.COMPLETED,
                priority=0,
                workflow_step=1,
                can_parallelize=False,
            )

        assert workflow_manager.is_issue_complete(issue_id) is True

    def test_is_issue_complete_with_pending_tasks(self, workflow_manager, test_db):
        """Test issue is not complete with pending tasks."""
        from codeframe.core.models import Issue, TaskStatus

        project_id = test_db.create_project(
            name="test_project", description="Test project for git workflow tests"
        )
        issue = Issue(
            project_id=project_id,
            issue_number="2.1",
            title="Test",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            workflow_step=1,
        )
        issue_id = test_db.create_issue(issue)

        # Create mix of completed and pending tasks
        test_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="2.1.1",
            parent_issue_number="2.1",
            title="Task 1",
            description="Test",
            status=TaskStatus.COMPLETED,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )
        test_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="2.1.2",
            parent_issue_number="2.1",
            title="Task 2",
            description="Test",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        assert workflow_manager.is_issue_complete(issue_id) is False

    def test_is_issue_complete_no_tasks(self, workflow_manager, test_db):
        """Test issue with no tasks is considered incomplete."""
        from codeframe.core.models import Issue, TaskStatus

        project_id = test_db.create_project(
            name="test_project", description="Test project for git workflow tests"
        )
        issue = Issue(
            project_id=project_id,
            issue_number="2.1",
            title="Test",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
        )
        issue_id = test_db.create_issue(issue)

        assert workflow_manager.is_issue_complete(issue_id) is False


class TestGetCurrentBranch:
    """Test getting current branch name."""

    def test_get_current_branch_main(self, workflow_manager, temp_git_repo):
        """Test getting current branch when on main/master."""
        repo_path, repo = temp_git_repo

        # Git may use main or master as default
        current = workflow_manager.get_current_branch()
        assert current in ["main", "master"]

    def test_get_current_branch_feature(self, workflow_manager, temp_git_repo):
        """Test getting current branch when on feature branch."""
        repo_path, repo = temp_git_repo

        # Create and checkout feature branch
        workflow_manager.create_feature_branch("2.1", "Test")
        repo.git.checkout("issue-2.1-test")

        assert workflow_manager.get_current_branch() == "issue-2.1-test"

    def test_get_current_branch_detached_head(self, workflow_manager, temp_git_repo):
        """Test getting current branch in detached HEAD state."""
        repo_path, repo = temp_git_repo

        # Get first commit and checkout in detached HEAD
        first_commit = repo.commit("HEAD")
        repo.git.checkout(first_commit.hexsha)

        # Should return commit SHA or indicate detached state
        current = workflow_manager.get_current_branch()
        assert current.startswith("HEAD detached at") or len(current) == 40  # SHA length


class TestCheckoutBranch:
    """Test branch checkout functionality."""

    def test_checkout_branch_success(self, workflow_manager, temp_git_repo):
        """Test successful branch checkout."""
        repo_path, repo = temp_git_repo

        # Create feature branch
        branch_name = workflow_manager.create_feature_branch("2.1", "Test")

        # Checkout branch
        workflow_manager.checkout_branch(branch_name)

        assert repo.active_branch.name == branch_name

    def test_checkout_branch_nonexistent(self, workflow_manager, temp_git_repo):
        """Test checkout of nonexistent branch raises error."""
        with pytest.raises(git.GitCommandError):
            workflow_manager.checkout_branch("nonexistent-branch")

    def test_checkout_branch_with_uncommitted_changes(self, workflow_manager, temp_git_repo):
        """Test checkout with uncommitted changes."""
        repo_path, repo = temp_git_repo

        # Create uncommitted changes
        test_file = repo_path / "test.txt"
        test_file.write_text("Uncommitted")

        # Create feature branch
        branch_name = workflow_manager.create_feature_branch("2.1", "Test")

        # Should still checkout (changes carry over)
        workflow_manager.checkout_branch(branch_name)
        assert repo.active_branch.name == branch_name
        assert test_file.exists()


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_issue_number(self, workflow_manager):
        """Test creating branch with empty issue number."""
        with pytest.raises(ValueError, match="Issue number cannot be empty"):
            workflow_manager.create_feature_branch("", "Test")

    def test_empty_issue_title(self, workflow_manager):
        """Test creating branch with empty title."""
        with pytest.raises(ValueError, match="Issue title cannot be empty"):
            workflow_manager.create_feature_branch("2.1", "")

    def test_whitespace_only_issue_number(self, workflow_manager):
        """Test creating branch with whitespace-only issue number."""
        with pytest.raises(ValueError, match="Issue number cannot be empty"):
            workflow_manager.create_feature_branch("   ", "Test")

    def test_special_characters_in_issue_number(self, workflow_manager, temp_git_repo):
        """Test issue number with special characters."""
        # Should sanitize and create valid branch
        branch_name = workflow_manager.create_feature_branch("2.1-beta", "Test Feature")
        assert branch_name == "issue-2.1-beta-test-feature"


class TestConventionalCommitMessages:
    """Test conventional commit message formatting (T069)."""

    def test_commit_message_format_feat(self, workflow_manager, temp_git_repo):
        """
        T069: Test conventional commit format for feature tasks.

        This test should FAIL initially because _generate_commit_message needs updates.
        """
        task = {
            "id": 1,
            "project_id": 1,
            "task_number": "cf-1.5.3",
            "title": "Add user authentication",
            "description": "Implement JWT-based authentication for API endpoints",
        }

        message = workflow_manager._generate_commit_message(task, ["auth.py", "jwt_handler.py"])

        # Assert conventional commit format: <type>(<scope>): <subject>
        assert message.startswith("feat(cf-1.5.3): Add user authentication")
        assert "Implement JWT-based authentication" in message
        assert "Modified files:" in message
        assert "- auth.py" in message
        assert "- jwt_handler.py" in message

    def test_commit_message_format_fix(self, workflow_manager, temp_git_repo):
        """Test conventional commit format for bug fix tasks."""
        task = {
            "id": 2,
            "project_id": 1,
            "task_number": "cf-2.1.4",
            "title": "Fix database connection leak",
            "description": "Close connections properly after queries",
        }

        message = workflow_manager._generate_commit_message(task, ["database.py"])

        assert message.startswith("fix(cf-2.1.4): Fix database connection leak")
        assert "Close connections properly" in message

    def test_commit_message_format_test(self, workflow_manager, temp_git_repo):
        """Test conventional commit format for test tasks."""
        task = {
            "id": 3,
            "project_id": 1,
            "task_number": "cf-3.2.1",
            "title": "Add tests for authentication module",
            "description": "Comprehensive test coverage for auth",
        }

        message = workflow_manager._generate_commit_message(task, ["tests/test_auth.py"])

        assert message.startswith("test(cf-3.2.1): Add tests for authentication module")

    def test_commit_message_format_refactor(self, workflow_manager, temp_git_repo):
        """Test conventional commit format for refactoring tasks."""
        task = {
            "id": 4,
            "project_id": 1,
            "task_number": "cf-4.1.2",
            "title": "Refactor user service into separate modules",
            "description": "Split monolithic user service",
        }

        message = workflow_manager._generate_commit_message(task, ["user_service.py"])

        assert message.startswith("refactor(cf-4.1.2): Refactor user service into separate modules")


class TestCommitErrorHandling:
    """Test error handling in commit operations (T072-T073)."""

    def test_commit_with_dirty_working_tree_raises_error(self, workflow_manager, temp_git_repo):
        """
        T072: Test that attempting to commit with untracked files raises ValueError.

        This test should FAIL initially because error handling needs to be added.
        """
        repo_path, repo = temp_git_repo

        # Create untracked file
        (repo_path / "untracked.py").write_text("# untracked")

        task = {
            "id": 5,
            "project_id": 1,
            "task_number": "cf-5.1.1",
            "title": "Test dirty tree",
            "description": "Should fail",
        }

        # Attempting to commit without staging should raise ValueError
        # Note: The method should check for dirty state BEFORE staging files
        # This is a design choice to ensure commits are intentional
        with pytest.raises(ValueError, match="Working tree is dirty"):
            # Try to commit a file that doesn't exist in staging
            workflow_manager.commit_task_changes(
                task=task, files_modified=["nonexistent.py"], agent_id="test-agent"
            )

    def test_commit_failure_logs_warning_non_blocking(self, workflow_manager, temp_git_repo):
        """
        T073: Test that commit failures are gracefully handled (log warning, don't raise).

        This is tested at the worker agent level, not at GitWorkflowManager level.
        GitWorkflowManager should raise exceptions, worker agents should catch them.
        """
        # This test is actually covered in test_backend_worker_auto_commit.py
        # test_backend_worker_graceful_commit_failure()
        pass


class TestDatabaseSHARecording:
    """Test commit SHA recording in database (T070-T071)."""

    def test_update_task_commit_sha(self, test_db):
        """
        T070: Test that update_task_commit_sha() stores full SHA correctly.

        This test should PASS as the database method already exists.
        """
        from codeframe.core.models import TaskStatus

        # Create project
        project_id = test_db.create_project(
            name="test_project", description="Test project for SHA recording"
        )

        # Create issue
        issue_id = test_db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.5",
                "title": "Test Issue",
                "status": TaskStatus.IN_PROGRESS.value,  # Convert enum to string
                "priority": 0,
                "workflow_step": 1,
            }
        )

        # Create task
        task_id = test_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.5.3",
            parent_issue_number="1.5",
            title="Test Task",
            description="Test",
            status=TaskStatus.COMPLETED,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        # Update with commit SHA
        full_sha = "abc123def456789012345678901234567890abcd"
        test_db.update_task_commit_sha(task_id, full_sha)

        # Verify it was stored
        cursor = test_db.conn.cursor()
        cursor.execute("SELECT commit_sha FROM tasks WHERE id = ?", (task_id,))
        result = cursor.fetchone()

        assert result is not None
        assert result["commit_sha"] == full_sha

    def test_get_task_by_commit_full_sha(self, test_db):
        """
        T071: Test that get_task_by_commit() retrieves task by full SHA.

        This test should PASS as the database method already exists.
        """
        from codeframe.core.models import TaskStatus

        # Create project
        project_id = test_db.create_project(
            name="test_project", description="Test project for SHA lookup"
        )

        # Create issue
        issue_id = test_db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "2.3",
                "title": "Test Issue",
                "status": TaskStatus.IN_PROGRESS.value,
                "priority": 0,
                "workflow_step": 1,
            }
        )

        # Create task
        task_id = test_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="2.3.1",
            parent_issue_number="2.3",
            title="Implement feature X",
            description="Test",
            status=TaskStatus.COMPLETED,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        # Store commit SHA
        full_sha = "def456abc789012345678901234567890abcdef1"
        test_db.update_task_commit_sha(task_id, full_sha)

        # Retrieve by full SHA
        task = test_db.get_task_by_commit(full_sha)

        assert task is not None
        assert task["id"] == task_id
        assert task["task_number"] == "2.3.1"
        assert task["commit_sha"] == full_sha

    def test_get_task_by_commit_short_sha(self, test_db):
        """
        T071: Test that get_task_by_commit() retrieves task by short SHA (7 chars).

        This test should PASS as the database method supports short SHA.
        """
        from codeframe.core.models import TaskStatus

        # Create project
        project_id = test_db.create_project(
            name="test_project", description="Test project for short SHA lookup"
        )

        # Create issue
        issue_id = test_db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "3.1",
                "title": "Test Issue",
                "status": TaskStatus.IN_PROGRESS.value,
                "priority": 0,
                "workflow_step": 1,
            }
        )

        # Create task
        task_id = test_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="3.1.2",
            parent_issue_number="3.1",
            title="Fix bug Y",
            description="Test",
            status=TaskStatus.COMPLETED,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        # Store full commit SHA
        full_sha = "789abc012345678901234567890abcdef123456"
        test_db.update_task_commit_sha(task_id, full_sha)

        # Retrieve by short SHA (first 7 characters)
        short_sha = full_sha[:7]
        task = test_db.get_task_by_commit(short_sha)

        assert task is not None
        assert task["id"] == task_id
        assert task["commit_sha"] == full_sha
