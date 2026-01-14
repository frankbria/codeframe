"""Repository for Pull Request operations.

Handles database operations for GitHub Pull Request tracking.
Part of Sprint 11 - GitHub PR Integration.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import logging

from codeframe.persistence.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class PRRepository(BaseRepository):
    """Repository for pull request database operations."""

    def create_pr(
        self,
        project_id: int,
        issue_id: Optional[int],
        branch_name: str,
        title: str,
        body: str,
        base_branch: str,
        head_branch: str,
        status: str = "open",
    ) -> int:
        """Create a new pull request record.

        Args:
            project_id: Project ID this PR belongs to
            issue_id: Optional associated issue ID
            branch_name: Git branch name
            title: PR title
            body: PR description
            base_branch: Target branch (e.g., "main")
            head_branch: Source branch with changes
            status: Initial status (default: "open")

        Returns:
            PR ID

        Raises:
            sqlite3.IntegrityError: If project_id doesn't exist
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO pull_requests (
                project_id, issue_id, branch_name, title, body,
                base_branch, head_branch, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, issue_id, branch_name, title, body, base_branch, head_branch, status),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_pr(self, pr_id: int) -> Optional[Dict[str, Any]]:
        """Get a pull request by its ID.

        Args:
            pr_id: Pull request ID

        Returns:
            PR dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM pull_requests WHERE id = ?",
            (pr_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_pr_by_number(self, project_id: int, pr_number: int) -> Optional[Dict[str, Any]]:
        """Get a pull request by its GitHub PR number.

        Args:
            project_id: Project ID
            pr_number: GitHub PR number

        Returns:
            PR dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM pull_requests
            WHERE project_id = ? AND pr_number = ?
            """,
            (project_id, pr_number),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_prs(
        self, project_id: int, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List pull requests for a project.

        Args:
            project_id: Project ID
            status: Optional filter by status (open, merged, closed, draft)

        Returns:
            List of PR dictionaries
        """
        cursor = self.conn.cursor()

        if status:
            cursor.execute(
                """
                SELECT * FROM pull_requests
                WHERE project_id = ? AND status = ?
                ORDER BY created_at DESC
                """,
                (project_id, status),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM pull_requests
                WHERE project_id = ?
                ORDER BY created_at DESC
                """,
                (project_id,),
            )

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def update_pr_github_data(
        self,
        pr_id: int,
        pr_number: int,
        pr_url: str,
        github_created_at: datetime,
    ) -> None:
        """Update PR with data from GitHub API response.

        Args:
            pr_id: Local PR ID
            pr_number: GitHub PR number
            pr_url: GitHub PR URL
            github_created_at: When PR was created on GitHub
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE pull_requests
            SET pr_number = ?, pr_url = ?, github_created_at = ?
            WHERE id = ?
            """,
            (pr_number, pr_url, github_created_at.isoformat(), pr_id),
        )
        self.conn.commit()

    def update_pr_status(
        self,
        pr_id: int,
        status: str,
        merge_commit_sha: Optional[str] = None,
        merged_at: Optional[datetime] = None,
    ) -> None:
        """Update pull request status.

        Args:
            pr_id: PR ID
            status: New status (open, merged, closed, draft)
            merge_commit_sha: Merge commit SHA (for merged PRs)
            merged_at: When PR was merged (auto-set if not provided)
        """
        cursor = self.conn.cursor()
        now = datetime.now()

        if status == "merged":
            merged_at = merged_at or now
            cursor.execute(
                """
                UPDATE pull_requests
                SET status = ?, merge_commit_sha = ?, merged_at = ?
                WHERE id = ?
                """,
                (status, merge_commit_sha, merged_at.isoformat(), pr_id),
            )
        elif status == "closed":
            cursor.execute(
                """
                UPDATE pull_requests
                SET status = ?, closed_at = ?
                WHERE id = ?
                """,
                (status, now.isoformat(), pr_id),
            )
        else:
            cursor.execute(
                """
                UPDATE pull_requests
                SET status = ?
                WHERE id = ?
                """,
                (status, pr_id),
            )

        self.conn.commit()

    def get_pr_for_branch(
        self, project_id: int, branch_name: str
    ) -> Optional[Dict[str, Any]]:
        """Find a PR by branch name.

        Args:
            project_id: Project ID
            branch_name: Git branch name

        Returns:
            PR dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM pull_requests
            WHERE project_id = ? AND branch_name = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (project_id, branch_name),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def delete_pr(self, pr_id: int) -> int:
        """Delete a pull request record.

        Args:
            pr_id: PR ID

        Returns:
            Number of rows deleted
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM pull_requests WHERE id = ?", (pr_id,))
        self.conn.commit()
        return cursor.rowcount
