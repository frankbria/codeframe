"""Unit tests for PRRepository (TDD - written before implementation)."""

import pytest
from datetime import datetime

from codeframe.persistence.repositories.pr_repository import PRRepository


class TestPRRepository:
    """Tests for the PRRepository class."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a test database with schema."""
        import sqlite3
        from codeframe.persistence.schema_manager import SchemaManager

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Create schema
        schema_mgr = SchemaManager(conn)
        schema_mgr.create_schema()

        return conn

    @pytest.fixture
    def repo(self, db):
        """Create PRRepository instance."""
        return PRRepository(sync_conn=db)

    @pytest.fixture
    def project_id(self, db):
        """Create a test project and return its ID."""
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO projects (name, description, workspace_path, status, phase)
            VALUES ('Test Project', 'A test project', '/tmp/test', 'active', 'active')
            """
        )
        db.commit()
        return cursor.lastrowid

    @pytest.fixture
    def issue_id(self, db, project_id):
        """Create a test issue and return its ID."""
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO issues (project_id, issue_number, title, status, priority)
            VALUES (?, 'ISSUE-001', 'Test Issue', 'pending', 1)
            """,
            (project_id,),
        )
        db.commit()
        return cursor.lastrowid

    def test_create_pr_returns_id(self, repo, project_id, issue_id):
        """Test that create_pr returns the new PR ID."""
        pr_id = repo.create_pr(
            project_id=project_id,
            issue_id=issue_id,
            branch_name="feature/test-branch",
            title="Test PR",
            body="This is a test PR",
            base_branch="main",
            head_branch="feature/test-branch",
        )

        assert pr_id is not None
        assert isinstance(pr_id, int)
        assert pr_id > 0

    def test_create_pr_without_issue(self, repo, project_id):
        """Test creating a PR without an associated issue."""
        pr_id = repo.create_pr(
            project_id=project_id,
            issue_id=None,
            branch_name="feature/no-issue",
            title="PR without issue",
            body="No associated issue",
            base_branch="main",
            head_branch="feature/no-issue",
        )

        assert pr_id is not None
        assert isinstance(pr_id, int)

    def test_get_pr_by_id(self, repo, project_id, issue_id):
        """Test retrieving a PR by its ID."""
        pr_id = repo.create_pr(
            project_id=project_id,
            issue_id=issue_id,
            branch_name="feature/test",
            title="Test PR",
            body="Test body",
            base_branch="main",
            head_branch="feature/test",
        )

        pr = repo.get_pr(pr_id)

        assert pr is not None
        assert pr["id"] == pr_id
        assert pr["project_id"] == project_id
        assert pr["issue_id"] == issue_id
        assert pr["branch_name"] == "feature/test"
        assert pr["title"] == "Test PR"
        assert pr["body"] == "Test body"
        assert pr["base_branch"] == "main"
        assert pr["head_branch"] == "feature/test"
        assert pr["status"] == "open"

    def test_get_pr_not_found(self, repo):
        """Test that get_pr returns None for non-existent PR."""
        pr = repo.get_pr(99999)
        assert pr is None

    def test_update_pr_github_data(self, repo, project_id):
        """Test updating PR with GitHub response data."""
        pr_id = repo.create_pr(
            project_id=project_id,
            issue_id=None,
            branch_name="feature/gh-test",
            title="GitHub Test PR",
            body="Test",
            base_branch="main",
            head_branch="feature/gh-test",
        )

        github_created_at = datetime.now()
        repo.update_pr_github_data(
            pr_id=pr_id,
            pr_number=42,
            pr_url="https://github.com/owner/repo/pull/42",
            github_created_at=github_created_at,
        )

        pr = repo.get_pr(pr_id)
        assert pr["pr_number"] == 42
        assert pr["pr_url"] == "https://github.com/owner/repo/pull/42"

    def test_get_pr_by_number(self, repo, project_id):
        """Test retrieving a PR by its GitHub PR number."""
        pr_id = repo.create_pr(
            project_id=project_id,
            issue_id=None,
            branch_name="feature/numbered",
            title="Numbered PR",
            body="Test",
            base_branch="main",
            head_branch="feature/numbered",
        )
        repo.update_pr_github_data(
            pr_id=pr_id,
            pr_number=123,
            pr_url="https://github.com/owner/repo/pull/123",
            github_created_at=datetime.now(),
        )

        pr = repo.get_pr_by_number(project_id, 123)

        assert pr is not None
        assert pr["pr_number"] == 123
        assert pr["id"] == pr_id

    def test_get_pr_by_number_not_found(self, repo, project_id):
        """Test that get_pr_by_number returns None for non-existent PR."""
        pr = repo.get_pr_by_number(project_id, 99999)
        assert pr is None

    def test_list_prs_all(self, repo, project_id):
        """Test listing all PRs for a project."""
        # Create multiple PRs
        for i in range(3):
            repo.create_pr(
                project_id=project_id,
                issue_id=None,
                branch_name=f"feature/pr-{i}",
                title=f"PR {i}",
                body=f"Body {i}",
                base_branch="main",
                head_branch=f"feature/pr-{i}",
            )

        prs = repo.list_prs(project_id)

        assert len(prs) == 3

    def test_list_prs_by_status(self, repo, project_id):
        """Test listing PRs filtered by status."""
        # Create PRs with different statuses
        pr_id1 = repo.create_pr(
            project_id=project_id,
            issue_id=None,
            branch_name="feature/open",
            title="Open PR",
            body="Test",
            base_branch="main",
            head_branch="feature/open",
        )

        pr_id2 = repo.create_pr(
            project_id=project_id,
            issue_id=None,
            branch_name="feature/merged",
            title="Merged PR",
            body="Test",
            base_branch="main",
            head_branch="feature/merged",
        )
        repo.update_pr_status(pr_id2, "merged", merge_commit_sha="abc123")

        # List only open PRs
        open_prs = repo.list_prs(project_id, status="open")
        assert len(open_prs) == 1
        assert open_prs[0]["title"] == "Open PR"

        # List only merged PRs
        merged_prs = repo.list_prs(project_id, status="merged")
        assert len(merged_prs) == 1
        assert merged_prs[0]["title"] == "Merged PR"

    def test_update_pr_status_to_merged(self, repo, project_id):
        """Test updating PR status to merged."""
        pr_id = repo.create_pr(
            project_id=project_id,
            issue_id=None,
            branch_name="feature/merge",
            title="To Merge",
            body="Test",
            base_branch="main",
            head_branch="feature/merge",
        )

        repo.update_pr_status(pr_id, "merged", merge_commit_sha="def456")

        pr = repo.get_pr(pr_id)
        assert pr["status"] == "merged"
        assert pr["merge_commit_sha"] == "def456"
        assert pr["merged_at"] is not None

    def test_update_pr_status_to_closed(self, repo, project_id):
        """Test updating PR status to closed."""
        pr_id = repo.create_pr(
            project_id=project_id,
            issue_id=None,
            branch_name="feature/close",
            title="To Close",
            body="Test",
            base_branch="main",
            head_branch="feature/close",
        )

        repo.update_pr_status(pr_id, "closed")

        pr = repo.get_pr(pr_id)
        assert pr["status"] == "closed"
        assert pr["closed_at"] is not None

    def test_get_pr_for_branch(self, repo, project_id):
        """Test finding a PR by branch name."""
        repo.create_pr(
            project_id=project_id,
            issue_id=None,
            branch_name="feature/unique-branch",
            title="Unique Branch PR",
            body="Test",
            base_branch="main",
            head_branch="feature/unique-branch",
        )

        pr = repo.get_pr_for_branch(project_id, "feature/unique-branch")

        assert pr is not None
        assert pr["branch_name"] == "feature/unique-branch"

    def test_get_pr_for_branch_not_found(self, repo, project_id):
        """Test that get_pr_for_branch returns None for non-existent branch."""
        pr = repo.get_pr_for_branch(project_id, "feature/nonexistent")
        assert pr is None

    def test_create_pr_stores_created_at(self, repo, project_id):
        """Test that create_pr automatically sets created_at timestamp."""
        pr_id = repo.create_pr(
            project_id=project_id,
            issue_id=None,
            branch_name="feature/timestamp",
            title="Timestamp PR",
            body="Test",
            base_branch="main",
            head_branch="feature/timestamp",
        )

        pr = repo.get_pr(pr_id)
        assert pr["created_at"] is not None
