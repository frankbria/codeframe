"""Test suite for database git_branches table and methods.

Following TDD methodology: RED → GREEN → REFACTOR
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime

from codeframe.persistence.database import Database
from codeframe.core.models import Issue, TaskStatus


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
def test_project(test_db):
    """Create a test project."""
    from codeframe.core.models import ProjectStatus

    project_id = test_db.create_project("test_project", ProjectStatus.INIT)
    return project_id


@pytest.fixture
def test_issue(test_db, test_project):
    """Create a test issue."""
    issue = Issue(
        project_id=test_project,
        issue_number="2.1",
        title="Test Issue",
        description="Test description",
        status=TaskStatus.PENDING,
        priority=0,
        workflow_step=1,
    )
    issue_id = test_db.create_issue(issue)
    return issue_id


class TestGitBranchesSchema:
    """Test git_branches table schema."""

    def test_table_exists(self, test_db):
        """Test that git_branches table exists."""
        cursor = test_db.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='git_branches'")
        result = cursor.fetchone()
        assert result is not None

    def test_table_columns(self, test_db):
        """Test that git_branches table has correct columns."""
        cursor = test_db.conn.cursor()
        cursor.execute("PRAGMA table_info(git_branches)")
        columns = cursor.fetchall()

        column_names = [col[1] for col in columns]

        assert "id" in column_names
        assert "issue_id" in column_names
        assert "branch_name" in column_names
        assert "created_at" in column_names
        assert "merged_at" in column_names
        assert "merge_commit" in column_names
        assert "status" in column_names

    def test_status_constraint(self, test_db, test_issue):
        """Test that status column has CHECK constraint."""
        # Valid statuses should work
        test_db.create_git_branch(test_issue, "test-branch")

        # Invalid status should fail
        cursor = test_db.conn.cursor()
        with pytest.raises(Exception):  # sqlite3.IntegrityError
            cursor.execute(
                "INSERT INTO git_branches (issue_id, branch_name, status) VALUES (?, ?, ?)",
                (test_issue, "invalid-branch", "invalid_status"),
            )


class TestCreateGitBranch:
    """Test create_git_branch method."""

    def test_create_git_branch_basic(self, test_db, test_issue):
        """Test creating a git branch record."""
        branch_id = test_db.create_git_branch(test_issue, "issue-2.1-test-feature")

        assert branch_id is not None
        assert isinstance(branch_id, int)

        # Verify in database
        cursor = test_db.conn.cursor()
        cursor.execute("SELECT * FROM git_branches WHERE id = ?", (branch_id,))
        row = cursor.fetchone()

        assert row is not None
        assert row["issue_id"] == test_issue
        assert row["branch_name"] == "issue-2.1-test-feature"
        assert row["status"] == "active"
        assert row["merged_at"] is None
        assert row["merge_commit"] is None

    def test_create_git_branch_with_timestamp(self, test_db, test_issue):
        """Test that created_at timestamp is set."""
        branch_id = test_db.create_git_branch(test_issue, "test-branch")

        cursor = test_db.conn.cursor()
        cursor.execute("SELECT created_at FROM git_branches WHERE id = ?", (branch_id,))
        row = cursor.fetchone()

        assert row["created_at"] is not None
        # Verify it's a valid timestamp format
        created_at = row["created_at"]
        assert isinstance(created_at, str)
        # Should be in SQLite timestamp format (YYYY-MM-DD HH:MM:SS)
        datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")

    def test_create_git_branch_duplicate_issue(self, test_db, test_issue):
        """Test creating multiple branches for same issue (should be allowed)."""
        # Create first branch
        branch_id1 = test_db.create_git_branch(test_issue, "branch-1")

        # Create second branch for same issue
        branch_id2 = test_db.create_git_branch(test_issue, "branch-2")

        assert branch_id1 != branch_id2

        # Both should exist
        cursor = test_db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM git_branches WHERE issue_id = ?", (test_issue,))
        count = cursor.fetchone()[0]
        assert count == 2

    def test_create_git_branch_nonexistent_issue(self, test_db):
        """Test creating branch for nonexistent issue."""
        # Should fail due to foreign key constraint
        with pytest.raises(Exception):  # sqlite3.IntegrityError
            test_db.create_git_branch(99999, "test-branch")


class TestGetBranchForIssue:
    """Test get_branch_for_issue method."""

    def test_get_branch_for_issue_exists(self, test_db, test_issue):
        """Test getting branch for issue that has one."""
        branch_id = test_db.create_git_branch(test_issue, "test-branch")

        result = test_db.get_branch_for_issue(test_issue)

        assert result is not None
        assert result["id"] == branch_id
        assert result["issue_id"] == test_issue
        assert result["branch_name"] == "test-branch"
        assert result["status"] == "active"

    def test_get_branch_for_issue_not_found(self, test_db, test_issue):
        """Test getting branch for issue with no branches."""
        result = test_db.get_branch_for_issue(test_issue)

        assert result is None

    def test_get_branch_for_issue_multiple_branches(self, test_db, test_issue):
        """Test getting branch when issue has multiple branches (returns most recent)."""
        # Create multiple branches
        test_db.create_git_branch(test_issue, "branch-1")
        test_db.create_git_branch(test_issue, "branch-2")
        branch_id3 = test_db.create_git_branch(test_issue, "branch-3")

        result = test_db.get_branch_for_issue(test_issue)

        # Should return most recent (highest id)
        assert result is not None
        assert result["id"] == branch_id3
        assert result["branch_name"] == "branch-3"

    def test_get_branch_for_issue_only_active(self, test_db, test_issue):
        """Test getting only active branches (not merged)."""
        # Create active branch
        active_id = test_db.create_git_branch(test_issue, "active-branch")

        # Create and merge another branch
        merged_id = test_db.create_git_branch(test_issue, "merged-branch")
        test_db.mark_branch_merged(merged_id, "abc123")

        result = test_db.get_branch_for_issue(test_issue)

        # Should return active branch, not merged one
        assert result is not None
        assert result["id"] == active_id
        assert result["status"] == "active"


class TestMarkBranchMerged:
    """Test mark_branch_merged method."""

    def test_mark_branch_merged_success(self, test_db, test_issue):
        """Test marking a branch as merged."""
        branch_id = test_db.create_git_branch(test_issue, "test-branch")

        # Mark as merged
        result = test_db.mark_branch_merged(branch_id, "abc123def456")

        assert result == 1  # One row updated

        # Verify in database
        cursor = test_db.conn.cursor()
        cursor.execute("SELECT * FROM git_branches WHERE id = ?", (branch_id,))
        row = cursor.fetchone()

        assert row["status"] == "merged"
        assert row["merge_commit"] == "abc123def456"
        assert row["merged_at"] is not None

        # Verify merged_at is valid timestamp
        merged_at = row["merged_at"]
        datetime.strptime(merged_at, "%Y-%m-%d %H:%M:%S")

    def test_mark_branch_merged_nonexistent(self, test_db):
        """Test marking nonexistent branch as merged."""
        result = test_db.mark_branch_merged(99999, "abc123")

        assert result == 0  # No rows updated

    def test_mark_branch_merged_already_merged(self, test_db, test_issue):
        """Test marking already-merged branch (should update)."""
        branch_id = test_db.create_git_branch(test_issue, "test-branch")

        # Mark as merged first time
        test_db.mark_branch_merged(branch_id, "commit1")

        # Mark as merged again with different commit
        result = test_db.mark_branch_merged(branch_id, "commit2")

        assert result == 1

        # Should have updated commit hash
        cursor = test_db.conn.cursor()
        cursor.execute("SELECT merge_commit FROM git_branches WHERE id = ?", (branch_id,))
        row = cursor.fetchone()
        assert row["merge_commit"] == "commit2"


class TestGetBranchesByStatus:
    """Test querying branches by status."""

    def test_get_active_branches(self, test_db, test_issue):
        """Test getting all active branches."""
        # Create mix of branches
        active_id1 = test_db.create_git_branch(test_issue, "active-1")
        active_id2 = test_db.create_git_branch(test_issue, "active-2")

        merged_id = test_db.create_git_branch(test_issue, "merged-1")
        test_db.mark_branch_merged(merged_id, "abc123")

        # Get active branches
        branches = test_db.get_branches_by_status("active")

        assert len(branches) == 2
        branch_ids = [b["id"] for b in branches]
        assert active_id1 in branch_ids
        assert active_id2 in branch_ids
        assert merged_id not in branch_ids

    def test_get_merged_branches(self, test_db, test_issue):
        """Test getting all merged branches."""
        # Create branches
        active_id = test_db.create_git_branch(test_issue, "active-1")

        merged_id1 = test_db.create_git_branch(test_issue, "merged-1")
        test_db.mark_branch_merged(merged_id1, "abc123")

        merged_id2 = test_db.create_git_branch(test_issue, "merged-2")
        test_db.mark_branch_merged(merged_id2, "def456")

        # Get merged branches
        branches = test_db.get_branches_by_status("merged")

        assert len(branches) == 2
        branch_ids = [b["id"] for b in branches]
        assert merged_id1 in branch_ids
        assert merged_id2 in branch_ids
        assert active_id not in branch_ids

    def test_get_branches_by_status_empty(self, test_db):
        """Test getting branches when none exist."""
        branches = test_db.get_branches_by_status("active")

        assert len(branches) == 0
        assert branches == []


class TestGetAllBranchesForIssue:
    """Test getting all branches for an issue."""

    def test_get_all_branches_for_issue(self, test_db, test_issue):
        """Test getting all branches (active and merged) for an issue."""
        # Create multiple branches
        id1 = test_db.create_git_branch(test_issue, "branch-1")
        id2 = test_db.create_git_branch(test_issue, "branch-2")

        # Merge one
        test_db.mark_branch_merged(id1, "abc123")

        # Get all branches
        branches = test_db.get_all_branches_for_issue(test_issue)

        assert len(branches) == 2

        # Check both are present
        branch_names = [b["branch_name"] for b in branches]
        assert "branch-1" in branch_names
        assert "branch-2" in branch_names

    def test_get_all_branches_for_issue_none(self, test_db, test_issue):
        """Test getting branches for issue with none."""
        branches = test_db.get_all_branches_for_issue(test_issue)

        assert len(branches) == 0


class TestBranchCleanup:
    """Test branch cleanup and status transitions."""

    def test_mark_branch_abandoned(self, test_db, test_issue):
        """Test marking a branch as abandoned."""
        branch_id = test_db.create_git_branch(test_issue, "abandoned-branch")

        # Mark as abandoned
        result = test_db.mark_branch_abandoned(branch_id)

        assert result == 1

        # Verify status
        cursor = test_db.conn.cursor()
        cursor.execute("SELECT status FROM git_branches WHERE id = ?", (branch_id,))
        row = cursor.fetchone()
        assert row["status"] == "abandoned"

    def test_delete_branch_record(self, test_db, test_issue):
        """Test deleting a branch record."""
        branch_id = test_db.create_git_branch(test_issue, "temp-branch")

        # Delete record
        result = test_db.delete_git_branch(branch_id)

        assert result == 1

        # Verify deleted
        cursor = test_db.conn.cursor()
        cursor.execute("SELECT * FROM git_branches WHERE id = ?", (branch_id,))
        row = cursor.fetchone()
        assert row is None


class TestBranchStatistics:
    """Test branch statistics queries."""

    def test_count_branches_by_issue(self, test_db, test_project):
        """Test counting branches per issue."""
        # Create multiple issues
        issue1_id = test_db.create_issue(
            Issue(
                project_id=test_project,
                issue_number="1.1",
                title="Issue 1",
                status=TaskStatus.PENDING,
                priority=0,
                workflow_step=1,
            )
        )

        issue2_id = test_db.create_issue(
            Issue(
                project_id=test_project,
                issue_number="1.2",
                title="Issue 2",
                status=TaskStatus.PENDING,
                priority=0,
                workflow_step=1,
            )
        )

        # Create branches
        test_db.create_git_branch(issue1_id, "branch-1-1")
        test_db.create_git_branch(issue1_id, "branch-1-2")
        test_db.create_git_branch(issue2_id, "branch-2-1")

        # Count for issue 1
        count = test_db.count_branches_for_issue(issue1_id)
        assert count == 2

        # Count for issue 2
        count = test_db.count_branches_for_issue(issue2_id)
        assert count == 1

    def test_get_branch_statistics(self, test_db, test_issue):
        """Test getting overall branch statistics."""
        # Create branches in different states
        test_db.create_git_branch(test_issue, "active-1")
        test_db.create_git_branch(test_issue, "active-2")

        merged_id = test_db.create_git_branch(test_issue, "merged-1")
        test_db.mark_branch_merged(merged_id, "abc123")

        abandoned_id = test_db.create_git_branch(test_issue, "abandoned-1")
        test_db.mark_branch_abandoned(abandoned_id)

        # Get statistics
        stats = test_db.get_branch_statistics()

        assert stats["total"] == 4
        assert stats["active"] == 2
        assert stats["merged"] == 1
        assert stats["abandoned"] == 1
