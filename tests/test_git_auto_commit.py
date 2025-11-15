"""Tests for Git Auto-Commit functionality (cf-44)."""

import pytest
import tempfile
import git
from pathlib import Path
from codeframe.git.workflow_manager import GitWorkflowManager
from codeframe.persistence.database import Database
from codeframe.core.models import ProjectStatus


@pytest.fixture
def temp_git_repo(tmp_path):
    """Create a temporary git repository for testing."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git repo
    repo = git.Repo.init(repo_path)

    # Configure git user (required for commits)
    repo.config_writer().set_value("user", "name", "Test User").release()
    repo.config_writer().set_value("user", "email", "test@example.com").release()

    # Create initial commit
    readme = repo_path / "README.md"
    readme.write_text("# Test Project")
    repo.index.add(["README.md"])
    repo.index.commit("Initial commit")

    return repo_path


@pytest.fixture
def db(tmp_path):
    """Create a test database."""
    db_path = tmp_path / "test.db"
    database = Database(db_path)
    database.initialize()

    # Create a test project
    project_id = database.create_project("Test Project", ProjectStatus.ACTIVE)

    yield database

    database.close()


@pytest.fixture
def workflow_manager(temp_git_repo, db):
    """Create a GitWorkflowManager instance."""
    return GitWorkflowManager(temp_git_repo, db)


class TestCommitMessageGeneration:
    """Tests for commit message generation."""

    def test_generate_message_for_feat_task(self, workflow_manager):
        """Test generating commit message for a feature task."""
        task = {
            "id": 1,
            "task_number": "1.5.2",
            "title": "Implement user authentication",
            "description": "Add JWT token-based authentication for API endpoints",
        }
        files = ["codeframe/auth/user.py", "tests/test_auth.py"]

        message = workflow_manager._generate_commit_message(task, files)

        # Should follow conventional commit format
        assert message.startswith("feat(1.5.2):")
        assert "Implement user authentication" in message
        assert "codeframe/auth/user.py" in message
        assert "tests/test_auth.py" in message

    def test_generate_message_for_fix_task(self, workflow_manager):
        """Test generating commit message for a bugfix task."""
        task = {
            "id": 2,
            "task_number": "2.3.1",
            "title": "Fix authentication token expiry",
            "description": "Correct token validation to properly check expiration",
        }
        files = ["codeframe/auth/token.py"]

        message = workflow_manager._generate_commit_message(task, files)

        # Should detect "fix" from title
        assert message.startswith("fix(2.3.1):")
        assert "Fix authentication token expiry" in message

    def test_generate_message_for_test_task(self, workflow_manager):
        """Test generating commit message for a test task."""
        task = {
            "id": 3,
            "task_number": "1.5.4",
            "title": "Add unit tests for authentication",
            "description": "Write comprehensive test coverage for auth module",
        }
        files = ["tests/test_auth.py"]

        message = workflow_manager._generate_commit_message(task, files)

        # Should detect "test" from title
        assert message.startswith("test(1.5.4):")

    def test_infer_commit_type_from_keywords(self, workflow_manager):
        """Test commit type inference from task title keywords."""
        # Test "implement" → feat
        assert workflow_manager._infer_commit_type("Implement user login", "") == "feat"

        # Test "add" → feat
        assert workflow_manager._infer_commit_type("Add password hashing", "") == "feat"

        # Test "fix" → fix
        assert workflow_manager._infer_commit_type("Fix login bug", "") == "fix"

        # Test "refactor" → refactor
        assert workflow_manager._infer_commit_type("Refactor auth module", "") == "refactor"

        # Test "test" → test
        assert workflow_manager._infer_commit_type("Add tests for login", "") == "test"

        # Test "document" → docs
        assert workflow_manager._infer_commit_type("Document API endpoints", "") == "docs"

        # Default to "feat" if no keyword matches
        assert workflow_manager._infer_commit_type("Something else", "") == "feat"

    def test_generate_message_with_file_list(self, workflow_manager):
        """Test that generated message includes modified files."""
        task = {
            "id": 1,
            "task_number": "1.1.1",
            "title": "Create user model",
            "description": "Define User model with fields",
        }
        files = ["codeframe/models/user.py", "tests/test_user_model.py"]

        message = workflow_manager._generate_commit_message(task, files)

        # Should list all files
        assert "codeframe/models/user.py" in message
        assert "tests/test_user_model.py" in message

    def test_generate_message_without_description(self, workflow_manager):
        """Test generating message when task has no description."""
        task = {
            "id": 1,
            "task_number": "1.1.1",
            "title": "Create user model",
            "description": None,
        }
        files = ["codeframe/models/user.py"]

        message = workflow_manager._generate_commit_message(task, files)

        # Should still generate valid message
        assert message.startswith("feat(1.1.1):")
        assert "Create user model" in message


class TestCommitCreation:
    """Tests for git commit creation."""

    def test_commit_single_file_change(self, workflow_manager, temp_git_repo):
        """Test creating a commit with a single file change."""
        # Create a test file
        test_file = temp_git_repo / "test.py"
        test_file.write_text("print('hello')")

        task = {
            "id": 1,
            "project_id": 1,
            "task_number": "1.1.1",
            "title": "Add hello script",
            "description": "Simple hello world script",
        }
        files = ["test.py"]

        # Commit the changes
        commit_hash = workflow_manager.commit_task_changes(
            task=task, files_modified=files, agent_id="test-agent"
        )

        # Verify commit was created
        assert commit_hash is not None
        assert len(commit_hash) == 40  # SHA-1 hash is 40 chars

        # Verify commit exists in git log
        repo = git.Repo(temp_git_repo)
        commits = list(repo.iter_commits())
        assert len(commits) == 2  # Initial + our commit
        assert commits[0].hexsha == commit_hash

    def test_commit_multiple_files(self, workflow_manager, temp_git_repo):
        """Test creating a commit with multiple file changes."""
        # Create multiple test files
        file1 = temp_git_repo / "file1.py"
        file2 = temp_git_repo / "file2.py"
        file1.write_text("# File 1")
        file2.write_text("# File 2")

        task = {
            "id": 2,
            "project_id": 1,
            "task_number": "1.1.2",
            "title": "Add multiple files",
            "description": "Create file1 and file2",
        }
        files = ["file1.py", "file2.py"]

        commit_hash = workflow_manager.commit_task_changes(
            task=task, files_modified=files, agent_id="test-agent"
        )

        assert commit_hash is not None

        # Verify both files are in the commit
        repo = git.Repo(temp_git_repo)
        commit = repo.commit(commit_hash)
        changed_files = [item.a_path for item in commit.diff(commit.parents[0])]
        assert "file1.py" in changed_files
        assert "file2.py" in changed_files

    def test_commit_message_in_git_log(self, workflow_manager, temp_git_repo):
        """Test that commit message appears correctly in git log."""
        test_file = temp_git_repo / "hello.py"
        test_file.write_text("print('hello')")

        task = {
            "id": 1,
            "project_id": 1,
            "task_number": "1.5.3",
            "title": "Add hello script",
            "description": "Script for greeting",
        }

        commit_hash = workflow_manager.commit_task_changes(
            task=task, files_modified=["hello.py"], agent_id="test-agent"
        )

        # Get commit message from git
        repo = git.Repo(temp_git_repo)
        commit = repo.commit(commit_hash)

        assert "feat(1.5.3):" in commit.message
        assert "Add hello script" in commit.message

    def test_commit_on_feature_branch(self, workflow_manager, temp_git_repo):
        """Test that commit is created on current branch, not main."""
        # Create and checkout a feature branch
        repo = git.Repo(temp_git_repo)
        feature_branch = repo.create_head("feature-test")
        feature_branch.checkout()

        # Create file and commit
        test_file = temp_git_repo / "feature.py"
        test_file.write_text("# Feature")

        task = {
            "id": 1,
            "project_id": 1,
            "task_number": "2.1.1",
            "title": "Add feature",
            "description": "New feature",
        }

        commit_hash = workflow_manager.commit_task_changes(
            task=task, files_modified=["feature.py"], agent_id="test-agent"
        )

        # Verify commit is on feature branch
        assert repo.active_branch.name == "feature-test"
        assert commit_hash == repo.head.commit.hexsha

        # Verify commit is NOT on master (test repos use master not main)
        repo.heads.master.checkout()
        assert commit_hash != repo.head.commit.hexsha

    def test_commit_returns_valid_sha(self, workflow_manager, temp_git_repo):
        """Test that returned commit hash is a valid SHA-1."""
        test_file = temp_git_repo / "test.py"
        test_file.write_text("# Test")

        task = {
            "id": 1,
            "project_id": 1,
            "task_number": "1.1.1",
            "title": "Test commit",
            "description": None,
        }

        commit_hash = workflow_manager.commit_task_changes(
            task=task, files_modified=["test.py"], agent_id="test-agent"
        )

        # SHA-1 is 40 hexadecimal characters
        assert len(commit_hash) == 40
        assert all(c in "0123456789abcdef" for c in commit_hash)


class TestChangelogIntegration:
    """Tests for changelog database integration."""

    def test_record_commit_in_changelog(self, workflow_manager, temp_git_repo, db):
        """Test that commit is recorded in changelog table."""
        # Create test project
        project_id = 1

        # Create and commit file
        test_file = temp_git_repo / "test.py"
        test_file.write_text("# Test")

        task = {
            "id": 5,
            "project_id": project_id,
            "task_number": "1.2.1",
            "title": "Add feature",
            "description": "Feature description",
        }

        commit_hash = workflow_manager.commit_task_changes(
            task=task, files_modified=["test.py"], agent_id="backend-agent-1"
        )

        # Query changelog
        cursor = db.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM changelog
            WHERE task_id = ? AND action = 'commit'
        """,
            (task["id"],),
        )

        row = cursor.fetchone()
        assert row is not None

        entry = dict(row)
        assert entry["project_id"] == project_id
        assert entry["agent_id"] == "backend-agent-1"
        assert entry["task_id"] == task["id"]
        assert entry["action"] == "commit"

        # Verify details JSON
        import json

        details = json.loads(entry["details"])
        assert details["commit_hash"] == commit_hash
        assert "feat(1.2.1):" in details["commit_message"]
        assert "test.py" in details["files_modified"]

    def test_changelog_entry_structure(self, workflow_manager, temp_git_repo, db):
        """Test that changelog entry has correct structure."""
        test_file = temp_git_repo / "test.py"
        test_file.write_text("# Test")

        task = {
            "id": 10,
            "project_id": 1,
            "task_number": "3.1.1",
            "title": "Test task",
            "description": "Test description",
        }

        commit_hash = workflow_manager.commit_task_changes(
            task=task, files_modified=["test.py"], agent_id="test-agent"
        )

        # Get changelog entry
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM changelog WHERE task_id = ?", (task["id"],))
        entry = dict(cursor.fetchone())

        # Verify required fields
        assert "id" in entry
        assert "project_id" in entry
        assert "agent_id" in entry
        assert "task_id" in entry
        assert "action" in entry
        assert "details" in entry
        assert "timestamp" in entry

    def test_query_changelog_by_task(self, workflow_manager, temp_git_repo, db):
        """Test querying changelog entries by task_id."""
        test_file = temp_git_repo / "test.py"
        test_file.write_text("# Test")

        task = {
            "id": 15,
            "project_id": 1,
            "task_number": "4.1.1",
            "title": "Query test",
            "description": "Test querying",
        }

        workflow_manager.commit_task_changes(
            task=task, files_modified=["test.py"], agent_id="test-agent"
        )

        # Query by task_id
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM changelog WHERE task_id = ?", (task["id"],))
        entries = cursor.fetchall()

        assert len(entries) == 1
        assert dict(entries[0])["task_id"] == task["id"]

    def test_query_changelog_by_agent(self, workflow_manager, temp_git_repo, db):
        """Test querying changelog entries by agent_id."""
        test_file = temp_git_repo / "test.py"
        test_file.write_text("# Test")

        task = {
            "id": 20,
            "project_id": 1,
            "task_number": "5.1.1",
            "title": "Agent query test",
            "description": "Test agent query",
        }

        workflow_manager.commit_task_changes(
            task=task, files_modified=["test.py"], agent_id="backend-agent-1"
        )

        # Query by agent_id
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM changelog WHERE agent_id = ?", ("backend-agent-1",))
        entries = cursor.fetchall()

        assert len(entries) >= 1
        # Verify at least one entry matches our agent
        agent_ids = [dict(e)["agent_id"] for e in entries]
        assert "backend-agent-1" in agent_ids


class TestErrorHandling:
    """Tests for error handling."""

    def test_handle_empty_file_list(self, workflow_manager):
        """Test handling empty file list."""
        task = {
            "id": 1,
            "project_id": 1,
            "task_number": "1.1.1",
            "title": "Empty commit",
            "description": "No files",
        }

        # Should raise ValueError or skip commit
        with pytest.raises(ValueError, match="No files to commit"):
            workflow_manager.commit_task_changes(
                task=task, files_modified=[], agent_id="test-agent"
            )

    def test_handle_nonexistent_files(self, workflow_manager, temp_git_repo):
        """Test handling files that don't exist in working directory."""
        task = {
            "id": 1,
            "project_id": 1,
            "task_number": "1.1.1",
            "title": "Nonexistent files",
            "description": "Files don't exist",
        }

        # Should raise error for nonexistent files
        with pytest.raises(Exception):  # Could be git.GitCommandError or FileNotFoundError
            workflow_manager.commit_task_changes(
                task=task, files_modified=["nonexistent.py"], agent_id="test-agent"
            )

    def test_handle_missing_task_fields(self, workflow_manager, temp_git_repo):
        """Test handling task with missing required fields."""
        test_file = temp_git_repo / "test.py"
        test_file.write_text("# Test")

        # Task missing task_number
        task = {
            "id": 1,
            "project_id": 1,
            "title": "Test",
        }

        with pytest.raises(KeyError):
            workflow_manager.commit_task_changes(
                task=task, files_modified=["test.py"], agent_id="test-agent"
            )
