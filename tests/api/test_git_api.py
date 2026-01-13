"""Tests for Git REST API endpoints (#270).

This module tests the git router endpoints for:
- Branch creation and management
- Commit creation and listing
- Git status retrieval

Tests follow RED-GREEN-REFACTOR TDD cycle.
"""

import tempfile
from pathlib import Path
from typing import Generator
import pytest
import git


def get_app():
    """Get the current app instance after module reload.

    Imports app locally to ensure we get the freshly reloaded instance
    after api_client fixture reloads codeframe.ui.server.
    """
    from codeframe.ui.server import app

    return app


@pytest.fixture(scope="function")
def test_project_with_git(api_client) -> Generator[dict, None, None]:
    """Create a test project with an initialized git repository.

    Args:
        api_client: FastAPI test client

    Yields:
        Project dictionary with id, workspace_path, and git repo
    """
    db = get_app().state.db

    # Create temporary directory for git workspace
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace_path = Path(temp_dir) / "project"
        workspace_path.mkdir(parents=True)

        # Initialize git repository
        repo = git.Repo.init(workspace_path)

        # Create initial commit (required for branch operations)
        readme_path = workspace_path / "README.md"
        readme_path.write_text("# Test Project\n")
        repo.index.add(["README.md"])
        repo.index.commit("Initial commit")

        # Create project in database with workspace path
        project_id = db.create_project(
            name="Test Git Project",
            description="Test project for git API tests",
            workspace_path=str(workspace_path),
        )

        yield {
            "id": project_id,
            "workspace_path": str(workspace_path),
            "repo": repo,
        }


@pytest.fixture(scope="function")
def test_project_with_issue(test_project_with_git, api_client) -> Generator[dict, None, None]:
    """Create a test project with an issue for branch creation.

    Args:
        test_project_with_git: Project fixture with git repository
        api_client: FastAPI test client

    Yields:
        Dictionary with project_id, issue_id, issue_number, workspace_path
    """
    from codeframe.core.models import Issue

    db = get_app().state.db
    project = test_project_with_git

    # Create an issue for the project using Issue model
    issue = Issue(
        project_id=project["id"],
        issue_number="1.1",
        title="User Authentication",
        description="Implement user authentication feature",
        priority=1,
    )
    issue_id = db.create_issue(issue)

    yield {
        "project_id": project["id"],
        "issue_id": issue_id,
        "issue_number": "1.1",
        "issue_title": "User Authentication",
        "workspace_path": project["workspace_path"],
        "repo": project["repo"],
    }


@pytest.fixture(scope="function")
def test_project_with_task(test_project_with_issue, api_client) -> Generator[dict, None, None]:
    """Create a test project with a task for commit operations.

    Args:
        test_project_with_issue: Project fixture with issue
        api_client: FastAPI test client

    Yields:
        Dictionary with project_id, issue_id, task_id, workspace_path
    """
    from codeframe.core.models import Task, TaskStatus

    db = get_app().state.db
    project = test_project_with_issue

    # Create a task for the issue using Task model
    task = Task(
        project_id=project["project_id"],
        task_number="1.1.1",
        title="Implement login endpoint",
        description="Create POST /api/login endpoint",
        status=TaskStatus.IN_PROGRESS,
    )
    task_id = db.create_task(task)

    yield {
        **project,
        "task_id": task_id,
        "task_number": "1.1.1",
    }


# ============================================================================
# Branch Creation Tests
# ============================================================================


class TestGitBranchCreation:
    """Test branch creation endpoint: POST /api/projects/{id}/git/branches."""

    def test_create_branch_endpoint_exists(self, api_client, test_project_with_issue):
        """Test that POST /api/projects/{id}/git/branches endpoint exists."""
        project = test_project_with_issue
        response = api_client.post(
            f"/api/projects/{project['project_id']}/git/branches",
            json={
                "issue_number": project["issue_number"],
                "issue_title": project["issue_title"],
            },
        )
        # Should not return 404 (endpoint not found)
        assert response.status_code != 404

    def test_create_branch_returns_201(self, api_client, test_project_with_issue):
        """Test that successful branch creation returns 201."""
        project = test_project_with_issue
        response = api_client.post(
            f"/api/projects/{project['project_id']}/git/branches",
            json={
                "issue_number": project["issue_number"],
                "issue_title": project["issue_title"],
            },
        )
        assert response.status_code == 201

    def test_create_branch_returns_branch_name(self, api_client, test_project_with_issue):
        """Test that response includes branch_name."""
        project = test_project_with_issue
        response = api_client.post(
            f"/api/projects/{project['project_id']}/git/branches",
            json={
                "issue_number": project["issue_number"],
                "issue_title": project["issue_title"],
            },
        )
        data = response.json()
        assert "branch_name" in data
        assert data["branch_name"].startswith("issue-")

    def test_create_branch_includes_issue_number_in_name(self, api_client, test_project_with_issue):
        """Test that branch name includes issue number."""
        project = test_project_with_issue
        response = api_client.post(
            f"/api/projects/{project['project_id']}/git/branches",
            json={
                "issue_number": project["issue_number"],
                "issue_title": project["issue_title"],
            },
        )
        data = response.json()
        assert project["issue_number"] in data["branch_name"]

    def test_create_branch_returns_status(self, api_client, test_project_with_issue):
        """Test that response includes status as 'active'."""
        project = test_project_with_issue
        response = api_client.post(
            f"/api/projects/{project['project_id']}/git/branches",
            json={
                "issue_number": project["issue_number"],
                "issue_title": project["issue_title"],
            },
        )
        data = response.json()
        assert "status" in data
        assert data["status"] == "active"

    def test_create_branch_creates_git_branch(self, api_client, test_project_with_issue):
        """Test that branch is actually created in git repository."""
        project = test_project_with_issue
        response = api_client.post(
            f"/api/projects/{project['project_id']}/git/branches",
            json={
                "issue_number": project["issue_number"],
                "issue_title": project["issue_title"],
            },
        )
        data = response.json()

        # Verify branch exists in git
        repo = project["repo"]
        branch_names = [b.name for b in repo.branches]
        assert data["branch_name"] in branch_names

    def test_create_branch_project_not_found(self, api_client):
        """Test that non-existent project returns 404."""
        response = api_client.post(
            "/api/projects/99999/git/branches",
            json={
                "issue_number": "1.1",
                "issue_title": "Test Issue",
            },
        )
        assert response.status_code == 404

    def test_create_branch_requires_issue_number(self, api_client, test_project_with_issue):
        """Test that issue_number is required."""
        project = test_project_with_issue
        response = api_client.post(
            f"/api/projects/{project['project_id']}/git/branches",
            json={
                "issue_title": project["issue_title"],
            },
        )
        assert response.status_code == 422

    def test_create_branch_requires_issue_title(self, api_client, test_project_with_issue):
        """Test that issue_title is required."""
        project = test_project_with_issue
        response = api_client.post(
            f"/api/projects/{project['project_id']}/git/branches",
            json={
                "issue_number": project["issue_number"],
            },
        )
        assert response.status_code == 422

    def test_create_duplicate_branch_returns_409_conflict(self, api_client, test_project_with_issue):
        """Test that creating duplicate branch returns 409 Conflict."""
        project = test_project_with_issue

        # Create branch first time
        api_client.post(
            f"/api/projects/{project['project_id']}/git/branches",
            json={
                "issue_number": project["issue_number"],
                "issue_title": project["issue_title"],
            },
        )

        # Try to create same branch again - should return 409 Conflict
        response = api_client.post(
            f"/api/projects/{project['project_id']}/git/branches",
            json={
                "issue_number": project["issue_number"],
                "issue_title": project["issue_title"],
            },
        )
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()

    def test_create_branch_issue_not_found(self, api_client, test_project_with_git):
        """Test that creating branch with non-existent issue returns 404."""
        project = test_project_with_git
        response = api_client.post(
            f"/api/projects/{project['id']}/git/branches",
            json={
                "issue_number": "999.999",
                "issue_title": "Non-existent Issue",
            },
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# ============================================================================
# Branch Listing Tests
# ============================================================================


class TestGitBranchListing:
    """Test branch listing endpoint: GET /api/projects/{id}/git/branches."""

    def test_list_branches_endpoint_exists(self, api_client, test_project_with_git):
        """Test that GET /api/projects/{id}/git/branches endpoint exists."""
        project = test_project_with_git
        response = api_client.get(f"/api/projects/{project['id']}/git/branches")
        assert response.status_code != 404

    def test_list_branches_returns_200(self, api_client, test_project_with_git):
        """Test that successful request returns 200."""
        project = test_project_with_git
        response = api_client.get(f"/api/projects/{project['id']}/git/branches")
        assert response.status_code == 200

    def test_list_branches_returns_list(self, api_client, test_project_with_git):
        """Test that response is a list of branches."""
        project = test_project_with_git
        response = api_client.get(f"/api/projects/{project['id']}/git/branches")
        data = response.json()
        assert "branches" in data
        assert isinstance(data["branches"], list)

    def test_list_branches_empty_when_no_branches(self, api_client, test_project_with_git):
        """Test that empty list returned when no feature branches exist."""
        project = test_project_with_git
        response = api_client.get(f"/api/projects/{project['id']}/git/branches")
        data = response.json()
        assert data["branches"] == []

    def test_list_branches_includes_created_branch(self, api_client, test_project_with_issue):
        """Test that created branch appears in list."""
        project = test_project_with_issue

        # Create a branch
        create_response = api_client.post(
            f"/api/projects/{project['project_id']}/git/branches",
            json={
                "issue_number": project["issue_number"],
                "issue_title": project["issue_title"],
            },
        )
        created_branch = create_response.json()["branch_name"]

        # List branches
        response = api_client.get(f"/api/projects/{project['project_id']}/git/branches")
        data = response.json()

        branch_names = [b["branch_name"] for b in data["branches"]]
        assert created_branch in branch_names

    def test_list_branches_project_not_found(self, api_client):
        """Test that non-existent project returns 404."""
        response = api_client.get("/api/projects/99999/git/branches")
        assert response.status_code == 404


# ============================================================================
# Branch Details Tests
# ============================================================================


class TestGitBranchDetails:
    """Test branch details endpoint: GET /api/projects/{id}/git/branches/{name}."""

    def test_get_branch_endpoint_exists(self, api_client, test_project_with_issue):
        """Test that GET /api/projects/{id}/git/branches/{name} endpoint exists."""
        project = test_project_with_issue

        # Create a branch first
        create_response = api_client.post(
            f"/api/projects/{project['project_id']}/git/branches",
            json={
                "issue_number": project["issue_number"],
                "issue_title": project["issue_title"],
            },
        )
        branch_name = create_response.json()["branch_name"]

        response = api_client.get(
            f"/api/projects/{project['project_id']}/git/branches/{branch_name}"
        )
        assert response.status_code != 404

    def test_get_branch_returns_200(self, api_client, test_project_with_issue):
        """Test that successful request returns 200."""
        project = test_project_with_issue

        create_response = api_client.post(
            f"/api/projects/{project['project_id']}/git/branches",
            json={
                "issue_number": project["issue_number"],
                "issue_title": project["issue_title"],
            },
        )
        branch_name = create_response.json()["branch_name"]

        response = api_client.get(
            f"/api/projects/{project['project_id']}/git/branches/{branch_name}"
        )
        assert response.status_code == 200

    def test_get_branch_includes_required_fields(self, api_client, test_project_with_issue):
        """Test that response includes all required fields."""
        project = test_project_with_issue

        create_response = api_client.post(
            f"/api/projects/{project['project_id']}/git/branches",
            json={
                "issue_number": project["issue_number"],
                "issue_title": project["issue_title"],
            },
        )
        branch_name = create_response.json()["branch_name"]

        response = api_client.get(
            f"/api/projects/{project['project_id']}/git/branches/{branch_name}"
        )
        data = response.json()

        assert "id" in data
        assert "branch_name" in data
        assert "issue_id" in data
        assert "status" in data
        assert "created_at" in data

    def test_get_branch_not_found(self, api_client, test_project_with_git):
        """Test that non-existent branch returns 404."""
        project = test_project_with_git
        response = api_client.get(
            f"/api/projects/{project['id']}/git/branches/nonexistent-branch"
        )
        assert response.status_code == 404


# ============================================================================
# Commit Creation Tests
# ============================================================================


class TestGitCommitCreation:
    """Test commit creation endpoint: POST /api/projects/{id}/git/commit."""

    def test_commit_endpoint_exists(self, api_client, test_project_with_task):
        """Test that POST /api/projects/{id}/git/commit endpoint exists."""
        project = test_project_with_task

        # Create a file to commit
        workspace_path = Path(project["workspace_path"])
        test_file = workspace_path / "test.py"
        test_file.write_text("# Test file\n")

        response = api_client.post(
            f"/api/projects/{project['project_id']}/git/commit",
            json={
                "task_id": project["task_id"],
                "files_modified": ["test.py"],
                "agent_id": "backend-worker-001",
            },
        )
        assert response.status_code != 404

    def test_commit_returns_201(self, api_client, test_project_with_task):
        """Test that successful commit returns 201."""
        project = test_project_with_task

        # Create a file to commit
        workspace_path = Path(project["workspace_path"])
        test_file = workspace_path / "auth.py"
        test_file.write_text("# Authentication module\n")

        response = api_client.post(
            f"/api/projects/{project['project_id']}/git/commit",
            json={
                "task_id": project["task_id"],
                "files_modified": ["auth.py"],
                "agent_id": "backend-worker-001",
            },
        )
        assert response.status_code == 201

    def test_commit_returns_commit_hash(self, api_client, test_project_with_task):
        """Test that response includes commit_hash."""
        project = test_project_with_task

        workspace_path = Path(project["workspace_path"])
        test_file = workspace_path / "login.py"
        test_file.write_text("# Login endpoint\n")

        response = api_client.post(
            f"/api/projects/{project['project_id']}/git/commit",
            json={
                "task_id": project["task_id"],
                "files_modified": ["login.py"],
                "agent_id": "backend-worker-001",
            },
        )
        data = response.json()

        assert "commit_hash" in data
        assert len(data["commit_hash"]) == 40  # Full SHA hash

    def test_commit_returns_commit_message(self, api_client, test_project_with_task):
        """Test that response includes commit_message."""
        project = test_project_with_task

        workspace_path = Path(project["workspace_path"])
        test_file = workspace_path / "session.py"
        test_file.write_text("# Session management\n")

        response = api_client.post(
            f"/api/projects/{project['project_id']}/git/commit",
            json={
                "task_id": project["task_id"],
                "files_modified": ["session.py"],
                "agent_id": "backend-worker-001",
            },
        )
        data = response.json()

        assert "commit_message" in data
        assert isinstance(data["commit_message"], str)

    def test_commit_requires_task_id(self, api_client, test_project_with_task):
        """Test that task_id is required."""
        project = test_project_with_task
        response = api_client.post(
            f"/api/projects/{project['project_id']}/git/commit",
            json={
                "files_modified": ["test.py"],
                "agent_id": "backend-worker-001",
            },
        )
        assert response.status_code == 422

    def test_commit_requires_files_modified(self, api_client, test_project_with_task):
        """Test that files_modified is required."""
        project = test_project_with_task
        response = api_client.post(
            f"/api/projects/{project['project_id']}/git/commit",
            json={
                "task_id": project["task_id"],
                "agent_id": "backend-worker-001",
            },
        )
        assert response.status_code == 422

    def test_commit_requires_agent_id(self, api_client, test_project_with_task):
        """Test that agent_id is required."""
        project = test_project_with_task
        response = api_client.post(
            f"/api/projects/{project['project_id']}/git/commit",
            json={
                "task_id": project["task_id"],
                "files_modified": ["test.py"],
            },
        )
        assert response.status_code == 422

    def test_commit_rejects_empty_files_list(self, api_client, test_project_with_task):
        """Test that empty files_modified list is rejected."""
        project = test_project_with_task
        response = api_client.post(
            f"/api/projects/{project['project_id']}/git/commit",
            json={
                "task_id": project["task_id"],
                "files_modified": [],
                "agent_id": "backend-worker-001",
            },
        )
        # Pydantic validation returns 422 for min_length constraint
        assert response.status_code == 422

    def test_commit_project_not_found(self, api_client):
        """Test that non-existent project returns 404."""
        response = api_client.post(
            "/api/projects/99999/git/commit",
            json={
                "task_id": 1,
                "files_modified": ["test.py"],
                "agent_id": "backend-worker-001",
            },
        )
        assert response.status_code == 404

    def test_commit_task_not_found(self, api_client, test_project_with_git):
        """Test that non-existent task returns 404."""
        project = test_project_with_git
        response = api_client.post(
            f"/api/projects/{project['id']}/git/commit",
            json={
                "task_id": 99999,
                "files_modified": ["test.py"],
                "agent_id": "backend-worker-001",
            },
        )
        assert response.status_code == 404

    def test_commit_rejects_absolute_paths(self, api_client, test_project_with_task):
        """Test that absolute file paths are rejected (security)."""
        project = test_project_with_task
        response = api_client.post(
            f"/api/projects/{project['project_id']}/git/commit",
            json={
                "task_id": project["task_id"],
                "files_modified": ["/etc/passwd"],
                "agent_id": "backend-worker-001",
            },
        )
        assert response.status_code == 400
        assert "absolute" in response.json()["detail"].lower()

    def test_commit_rejects_path_traversal(self, api_client, test_project_with_task):
        """Test that path traversal attempts are rejected (security)."""
        project = test_project_with_task
        response = api_client.post(
            f"/api/projects/{project['project_id']}/git/commit",
            json={
                "task_id": project["task_id"],
                "files_modified": ["../../../etc/passwd"],
                "agent_id": "backend-worker-001",
            },
        )
        assert response.status_code == 400
        assert "traversal" in response.json()["detail"].lower()

    def test_commit_rejects_workspace_escape(self, api_client, test_project_with_task):
        """Test that paths escaping workspace are rejected (security)."""
        project = test_project_with_task
        # Use a path that doesn't have '..' but could resolve outside via symlinks
        # This tests the commonpath check
        response = api_client.post(
            f"/api/projects/{project['project_id']}/git/commit",
            json={
                "task_id": project["task_id"],
                "files_modified": ["subdir/../../../outside.txt"],
                "agent_id": "backend-worker-001",
            },
        )
        assert response.status_code == 400


# ============================================================================
# Commit Listing Tests
# ============================================================================


class TestGitCommitListing:
    """Test commit listing endpoint: GET /api/projects/{id}/git/commits."""

    def test_list_commits_endpoint_exists(self, api_client, test_project_with_git):
        """Test that GET /api/projects/{id}/git/commits endpoint exists."""
        project = test_project_with_git
        response = api_client.get(f"/api/projects/{project['id']}/git/commits")
        assert response.status_code != 404

    def test_list_commits_returns_200(self, api_client, test_project_with_git):
        """Test that successful request returns 200."""
        project = test_project_with_git
        response = api_client.get(f"/api/projects/{project['id']}/git/commits")
        assert response.status_code == 200

    def test_list_commits_returns_list(self, api_client, test_project_with_git):
        """Test that response is a list of commits."""
        project = test_project_with_git
        response = api_client.get(f"/api/projects/{project['id']}/git/commits")
        data = response.json()
        assert "commits" in data
        assert isinstance(data["commits"], list)

    def test_list_commits_includes_initial_commit(self, api_client, test_project_with_git):
        """Test that initial commit is included in list."""
        project = test_project_with_git
        response = api_client.get(f"/api/projects/{project['id']}/git/commits")
        data = response.json()

        # Should have at least the initial commit
        assert len(data["commits"]) >= 1

    def test_list_commits_with_limit(self, api_client, test_project_with_git):
        """Test that limit parameter works."""
        project = test_project_with_git
        response = api_client.get(f"/api/projects/{project['id']}/git/commits?limit=1")
        data = response.json()

        assert len(data["commits"]) <= 1

    def test_list_commits_commit_has_required_fields(self, api_client, test_project_with_git):
        """Test that each commit has required fields."""
        project = test_project_with_git
        response = api_client.get(f"/api/projects/{project['id']}/git/commits")
        data = response.json()

        if data["commits"]:
            commit = data["commits"][0]
            assert "hash" in commit
            assert "short_hash" in commit
            assert "message" in commit
            assert "author" in commit
            assert "timestamp" in commit

    def test_list_commits_project_not_found(self, api_client):
        """Test that non-existent project returns 404."""
        response = api_client.get("/api/projects/99999/git/commits")
        assert response.status_code == 404


# ============================================================================
# Git Status Tests
# ============================================================================


class TestGitStatus:
    """Test git status endpoint: GET /api/projects/{id}/git/status."""

    def test_status_endpoint_exists(self, api_client, test_project_with_git):
        """Test that GET /api/projects/{id}/git/status endpoint exists."""
        project = test_project_with_git
        response = api_client.get(f"/api/projects/{project['id']}/git/status")
        assert response.status_code != 404

    def test_status_returns_200(self, api_client, test_project_with_git):
        """Test that successful request returns 200."""
        project = test_project_with_git
        response = api_client.get(f"/api/projects/{project['id']}/git/status")
        assert response.status_code == 200

    def test_status_includes_current_branch(self, api_client, test_project_with_git):
        """Test that response includes current_branch."""
        project = test_project_with_git
        response = api_client.get(f"/api/projects/{project['id']}/git/status")
        data = response.json()

        assert "current_branch" in data
        assert isinstance(data["current_branch"], str)

    def test_status_includes_is_dirty(self, api_client, test_project_with_git):
        """Test that response includes is_dirty flag."""
        project = test_project_with_git
        response = api_client.get(f"/api/projects/{project['id']}/git/status")
        data = response.json()

        assert "is_dirty" in data
        assert isinstance(data["is_dirty"], bool)

    def test_status_includes_file_lists(self, api_client, test_project_with_git):
        """Test that response includes file status lists."""
        project = test_project_with_git
        response = api_client.get(f"/api/projects/{project['id']}/git/status")
        data = response.json()

        assert "modified_files" in data
        assert "untracked_files" in data
        assert "staged_files" in data
        assert isinstance(data["modified_files"], list)
        assert isinstance(data["untracked_files"], list)
        assert isinstance(data["staged_files"], list)

    def test_status_clean_repo(self, api_client, test_project_with_git):
        """Test status on clean repository."""
        project = test_project_with_git
        response = api_client.get(f"/api/projects/{project['id']}/git/status")
        data = response.json()

        assert data["is_dirty"] is False
        assert data["modified_files"] == []
        assert data["untracked_files"] == []

    def test_status_with_untracked_file(self, api_client, test_project_with_git):
        """Test status with untracked files."""
        project = test_project_with_git

        # Create an untracked file
        workspace_path = Path(project["workspace_path"])
        new_file = workspace_path / "new_file.py"
        new_file.write_text("# New file\n")

        response = api_client.get(f"/api/projects/{project['id']}/git/status")
        data = response.json()

        assert data["is_dirty"] is True
        assert "new_file.py" in data["untracked_files"]

    def test_status_project_not_found(self, api_client):
        """Test that non-existent project returns 404."""
        response = api_client.get("/api/projects/99999/git/status")
        assert response.status_code == 404


# ============================================================================
# Authorization Tests
# ============================================================================


class TestGitApiAuthorization:
    """Test authorization for git API endpoints."""

    def test_create_branch_requires_auth(self, api_client, test_project_with_issue):
        """Test that branch creation requires authentication."""
        project = test_project_with_issue

        # Remove auth header
        del api_client.headers["Authorization"]

        response = api_client.post(
            f"/api/projects/{project['project_id']}/git/branches",
            json={
                "issue_number": project["issue_number"],
                "issue_title": project["issue_title"],
            },
        )

        # Restore auth header for cleanup
        from tests.api.conftest import create_test_jwt_token
        api_client.headers["Authorization"] = f"Bearer {create_test_jwt_token()}"

        assert response.status_code == 401
