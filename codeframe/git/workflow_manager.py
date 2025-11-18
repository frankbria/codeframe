"""Git workflow manager for CodeFRAME issues and feature branches.

Manages git branching and merge workflows:
- Feature branch creation per issue
- Auto-merge to main when all tasks complete
- Database tracking of branches
"""

import re
import logging
from pathlib import Path
from typing import Dict, Any, List
import git

from codeframe.persistence.database import Database

logger = logging.getLogger(__name__)


class GitWorkflowManager:
    """Manages git branching and merge workflows for CodeFRAME issues."""

    def __init__(self, project_root: Path, db: Database):
        """Initialize GitWorkflowManager.

        Args:
            project_root: Path to project root (must be a git repository)
            db: Database instance for tracking branches

        Raises:
            git.InvalidGitRepositoryError: If project_root is not a git repository
            git.NoSuchPathError: If project_root does not exist
        """
        self.project_root = Path(project_root)
        self.db = db

        # Initialize git repo
        self.repo = git.Repo(self.project_root)

        logger.info(f"Initialized GitWorkflowManager for {self.project_root}")

    def create_feature_branch(self, issue_number: str, issue_title: str) -> str:
        """Create feature branch for an issue.

        Branch naming convention: issue-{issue_number}-{sanitized-title}
        Example: issue-2.1-user-authentication

        Args:
            issue_number: Issue number (e.g., "2.1", "3.5")
            issue_title: Issue title for branch name

        Returns:
            Branch name created (e.g., "issue-2.1-user-authentication")

        Raises:
            ValueError: If issue_number or issue_title is empty/invalid
            ValueError: If branch already exists
        """
        # Validate inputs
        if not issue_number or not issue_number.strip():
            raise ValueError("Issue number cannot be empty")
        if not issue_title or not issue_title.strip():
            raise ValueError("Issue title cannot be empty")

        # Sanitize issue number and title for branch name
        issue_number_clean = issue_number.strip()
        title_clean = self._sanitize_branch_name(issue_title)

        # Construct branch name
        branch_name = f"issue-{issue_number_clean}-{title_clean}"

        # Truncate if too long (git ref name limit ~63 chars)
        if len(branch_name) > 63:
            # Keep issue prefix, truncate title part
            prefix = f"issue-{issue_number_clean}-"
            max_title_len = 63 - len(prefix)
            title_clean = title_clean[:max_title_len]
            branch_name = f"{prefix}{title_clean}"

        # Check if branch already exists
        if branch_name in [b.name for b in self.repo.branches]:
            raise ValueError(f"Branch '{branch_name}' already exists")

        # Create branch from current HEAD
        new_branch = self.repo.create_head(branch_name)

        logger.info(f"Created feature branch: {branch_name}")

        # Store in database (if issue exists)
        try:
            # Find issue by issue_number across all projects
            # Get all projects to find matching issue
            projects = self.db.list_projects()
            matching_issue = None

            for project in projects:
                issues = self.db.get_project_issues(project["id"])
                matches = [i for i in issues if i["issue_number"] == issue_number_clean]
                if matches:
                    matching_issue = matches[0]
                    break

            if matching_issue:
                self.db.create_git_branch(matching_issue["id"], branch_name)
                logger.debug(
                    f"Stored branch {branch_name} in database for issue {matching_issue['id']}"
                )
        except Exception as e:
            logger.warning(f"Could not store branch in database: {e}")
            # Don't fail if database tracking fails

        return branch_name

    def _sanitize_branch_name(self, title: str) -> str:
        """Sanitize title for use in git branch name.

        Args:
            title: Raw title string

        Returns:
            Sanitized string safe for git branch names
        """
        # Convert to lowercase
        sanitized = title.lower()

        # Replace spaces and special characters with hyphens
        sanitized = re.sub(r"[^\w\s-]", "", sanitized)  # Remove special chars
        sanitized = re.sub(r"[\s_]+", "-", sanitized)  # Replace spaces/underscores with hyphens
        sanitized = re.sub(r"-+", "-", sanitized)  # Collapse multiple hyphens
        sanitized = sanitized.strip("-")  # Remove leading/trailing hyphens

        return sanitized

    def merge_to_main(self, issue_number: str) -> Dict[str, Any]:
        """Merge feature branch to main after all tasks complete.

        Args:
            issue_number: Issue number to merge (e.g., "2.1")

        Returns:
            dict with merge_commit, branch_name, status

        Raises:
            ValueError: If issue not found or tasks incomplete
            git.GitCommandError: If merge conflicts occur
        """
        # Find issue by number across all projects
        projects = self.db.list_projects()
        matching_issue = None

        for project in projects:
            issues = self.db.get_project_issues(project["id"])
            matches = [i for i in issues if i["issue_number"] == issue_number]
            if matches:
                matching_issue = matches[0]
                break

        if not matching_issue:
            raise ValueError(f"Issue {issue_number} not found")

        issue_id = matching_issue["id"]

        # Check all tasks are completed
        if not self.is_issue_complete(issue_id):
            raise ValueError(f"Cannot merge issue {issue_number}: incomplete tasks remain")

        # Get branch name from database
        branch_record = self.db.get_branch_for_issue(issue_id)
        if not branch_record:
            raise ValueError(f"No branch found for issue {issue_number}")

        branch_name = branch_record["branch_name"]

        # Ensure we're on main/master branch
        try:
            main_branch = self.repo.heads.main
        except AttributeError:
            # Fall back to master if main doesn't exist
            main_branch = self.repo.heads.master

        main_branch.checkout()

        # Perform merge
        try:
            # Merge with no-ff to preserve branch history
            self.repo.git.merge(branch_name, no_ff=True, m=f"Merge {branch_name}")

            # Get merge commit
            merge_commit = self.repo.head.commit.hexsha

            logger.info(f"Merged {branch_name} to main: {merge_commit}")

            # Update database
            self.db.mark_branch_merged(branch_record["id"], merge_commit)

            return {
                "status": "merged",
                "branch_name": branch_name,
                "merge_commit": merge_commit,
            }

        except git.GitCommandError as e:
            logger.error(f"Merge conflict occurred: {e}")
            # Abort merge
            try:
                self.repo.git.merge("--abort")
            except:
                pass
            raise

    def is_issue_complete(self, issue_id: int) -> bool:
        """Check if all tasks for an issue are completed.

        Args:
            issue_id: Issue ID

        Returns:
            True if all tasks completed, False otherwise
        """
        tasks = self.db.get_tasks_by_issue(issue_id)

        # No tasks = incomplete
        if not tasks:
            return False

        # Check all tasks are completed
        all_completed = all(task["status"] == "completed" for task in tasks)

        logger.debug(
            f"Issue {issue_id} completion check: {len(tasks)} tasks, " f"completed={all_completed}"
        )

        return all_completed

    def get_current_branch(self) -> str:
        """Get current git branch name.

        Returns:
            Current branch name, or "HEAD detached at {sha}" if in detached HEAD state
        """
        try:
            return self.repo.active_branch.name
        except TypeError:
            # Detached HEAD state
            commit_sha = self.repo.head.commit.hexsha[:7]
            return f"HEAD detached at {commit_sha}"

    def checkout_branch(self, branch_name: str) -> None:
        """Checkout a git branch.

        Args:
            branch_name: Name of branch to checkout

        Raises:
            git.GitCommandError: If branch does not exist or checkout fails
        """
        self.repo.git.checkout(branch_name)
        logger.info(f"Checked out branch: {branch_name}")

    def _infer_commit_type(self, title: str, description: str) -> str:
        """Infer conventional commit type from task title and description.

        Args:
            title: Task title
            description: Task description

        Returns:
            Commit type (feat, fix, refactor, test, docs, chore)
        """
        # Combine title and description for keyword matching
        text = (title + " " + (description or "")).lower()

        # Check for keywords
        if any(kw in text for kw in ["fix", "bug", "repair", "correct"]):
            return "fix"
        elif any(kw in text for kw in ["test", "testing", "spec"]):
            return "test"
        elif any(kw in text for kw in ["refactor", "restructure", "reorganize"]):
            return "refactor"
        elif any(kw in text for kw in ["document", "docs", "readme"]):
            return "docs"
        elif any(kw in text for kw in ["chore", "config", "setup"]):
            return "chore"
        else:
            # Default to "feat" for implementation tasks
            return "feat"

    def _generate_commit_message(self, task: Dict[str, Any], files_modified: List[str]) -> str:
        """Generate conventional commit message from task.

        Args:
            task: Task dictionary with task_number, title, description
            files_modified: List of modified file paths

        Returns:
            Conventional commit message string
        """
        # Infer commit type
        commit_type = self._infer_commit_type(task["title"], task.get("description", ""))

        # Build message
        scope = task["task_number"]
        subject = task["title"]

        # Start with conventional format
        message = f"{commit_type}({scope}): {subject}"

        # Add body with description if present
        if task.get("description"):
            message += f"\n\n{task['description']}"

        # Add file listing
        if files_modified:
            message += "\n\nModified files:"
            for file_path in files_modified:
                message += f"\n- {file_path}"

        return message

    def commit_task_changes(
        self, task: Dict[str, Any], files_modified: List[str], agent_id: str
    ) -> str:
        """Create git commit for task changes and record in changelog.

        Args:
            task: Task dictionary with id, project_id, task_number, title, description
            files_modified: List of file paths that were modified
            agent_id: ID of agent making the commit

        Returns:
            Commit SHA hash

        Raises:
            ValueError: If files_modified is empty or working tree is dirty
            KeyError: If task missing required fields
            git.GitCommandError: If git operations fail
        """
        # Validate inputs
        if not files_modified:
            raise ValueError("No files to commit")

        # Ensure required task fields exist
        required_fields = ["id", "project_id", "task_number", "title"]
        for field in required_fields:
            if field not in task:
                raise KeyError(f"Task missing required field: {field}")

        # T079: Check for dirty working tree BEFORE staging files
        # Note: We allow modified files that we're about to stage, but not untracked files
        # or other modifications that aren't part of files_modified
        if self.repo.is_dirty(untracked_files=True):
            # Check if the dirty files are the ones we're about to commit
            dirty_files = [item.a_path for item in self.repo.index.diff(None)]
            dirty_files.extend(self.repo.untracked_files)

            # Remove files we're about to stage from dirty list
            non_staged_dirty = [f for f in dirty_files if f not in files_modified]

            if non_staged_dirty:
                raise ValueError(
                    f"Working tree is dirty - cannot commit. "
                    f"Unrelated changes detected: {', '.join(non_staged_dirty[:3])}"
                )

        # Generate commit message
        commit_message = self._generate_commit_message(task, files_modified)

        # Stage files
        self.repo.index.add(files_modified)

        # Create commit
        commit = self.repo.index.commit(commit_message)
        commit_hash = commit.hexsha

        logger.info(f"Created commit {commit_hash[:7]} for task {task['task_number']}")

        # Record in changelog
        import json

        try:
            details = json.dumps(
                {
                    "commit_hash": commit_hash,
                    "commit_message": commit_message,
                    "files_modified": files_modified,
                }
            )

            cursor = self.db.conn.cursor()
            cursor.execute(
                """
                INSERT INTO changelog (project_id, agent_id, task_id, action, details)
                VALUES (?, ?, ?, ?, ?)
                """,
                (task["project_id"], agent_id, task["id"], "commit", details),
            )
            self.db.conn.commit()

            logger.debug(f"Recorded commit in changelog for task {task['id']}")
        except Exception as e:
            logger.warning(f"Failed to record commit in changelog: {e}")
            # Don't fail the commit if changelog recording fails

        return commit_hash
