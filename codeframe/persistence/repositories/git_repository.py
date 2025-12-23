"""Repository for Git Repository operations.

Extracted from monolithic Database class for better maintainability.
"""

import os
from datetime import datetime
from typing import List, Optional, Dict, Any
import logging


from codeframe.persistence.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

# Audit verbosity configuration
AUDIT_VERBOSITY = os.getenv("AUDIT_VERBOSITY", "low").lower()
if AUDIT_VERBOSITY not in ("low", "high"):
    logger.warning(f"Invalid AUDIT_VERBOSITY='{AUDIT_VERBOSITY}', defaulting to 'low'")
    AUDIT_VERBOSITY = "low"


class GitRepository(BaseRepository):
    """Repository for git repository operations."""

    def create_git_branch(self, issue_id: int, branch_name: str) -> int:
        """Create a git branch record.

        Args:
            issue_id: Issue ID this branch belongs to
            branch_name: Git branch name

        Returns:
            Branch ID

        Raises:
            sqlite3.IntegrityError: If issue_id doesn't exist
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO git_branches (issue_id, branch_name, status)
            VALUES (?, ?, ?)
            """,
            (issue_id, branch_name, "active"),
        )
        self.conn.commit()
        return cursor.lastrowid



    def get_branch_for_issue(self, issue_id: int) -> Optional[Dict[str, Any]]:
        """Get the most recent active branch for an issue.

        Args:
            issue_id: Issue ID

        Returns:
            Branch dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM git_branches
            WHERE issue_id = ? AND status = 'active'
            ORDER BY id DESC
            LIMIT 1
            """,
            (issue_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None



    def mark_branch_merged(self, branch_id: int, merge_commit: str) -> int:
        """Mark a branch as merged.

        Args:
            branch_id: Branch ID
            merge_commit: Git commit SHA of merge

        Returns:
            Number of rows updated
        """

        cursor = self.conn.cursor()
        merged_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            """
            UPDATE git_branches
            SET status = ?, merge_commit = ?, merged_at = ?
            WHERE id = ?
            """,
            ("merged", merge_commit, merged_at, branch_id),
        )
        self.conn.commit()
        return cursor.rowcount



    def mark_branch_abandoned(self, branch_id: int) -> int:
        """Mark a branch as abandoned.

        Args:
            branch_id: Branch ID

        Returns:
            Number of rows updated
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE git_branches SET status = ? WHERE id = ?",
            ("abandoned", branch_id),
        )
        self.conn.commit()
        return cursor.rowcount



    def get_branch_statistics(self) -> Dict[str, int]:
        """Get branch statistics across all statuses.

        Returns:
            Dictionary with total, active, merged, abandoned counts
        """
        cursor = self.conn.cursor()

        # Total count
        cursor.execute("SELECT COUNT(*) FROM git_branches")
        total = cursor.fetchone()[0]

        # Count by status
        stats = {"total": total}
        for status in ["active", "merged", "abandoned"]:
            cursor.execute(
                "SELECT COUNT(*) FROM git_branches WHERE status = ?",
                (status,),
            )
            stats[status] = cursor.fetchone()[0]

        return stats

    # Test Results methods (cf-42)


    def delete_git_branch(self, branch_id: int) -> int:
        """Delete a git branch record.

        Args:
            branch_id: Branch ID

        Returns:
            Number of rows deleted
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM git_branches WHERE id = ?", (branch_id,))
        self.conn.commit()
        return cursor.rowcount



    def get_branches_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get all branches with given status.

        Args:
            status: Branch status (active, merged, abandoned)

        Returns:
            List of branch dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM git_branches WHERE status = ? ORDER BY id",
            (status,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]



    def get_all_branches_for_issue(self, issue_id: int) -> List[Dict[str, Any]]:
        """Get all branches for an issue (all statuses).

        Args:
            issue_id: Issue ID

        Returns:
            List of branch dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM git_branches WHERE issue_id = ? ORDER BY id",
            (issue_id,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]



    def count_branches_for_issue(self, issue_id: int) -> int:
        """Count branches for an issue.

        Args:
            issue_id: Issue ID

        Returns:
            Number of branches
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM git_branches WHERE issue_id = ?",
            (issue_id,),
        )
        return cursor.fetchone()[0]

