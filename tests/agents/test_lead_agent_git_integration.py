"""Integration tests for LeadAgent git workflow methods.

Following TDD methodology: RED → GREEN → REFACTOR
Tests written FIRST before implementation.
"""

import os
import pytest
import tempfile
from pathlib import Path
import git

from codeframe.agents.lead_agent import LeadAgent
from codeframe.persistence.database import Database
from codeframe.core.models import Issue, TaskStatus


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

        # Create deploy script for tests
        scripts_dir = repo_path / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        deploy_script = scripts_dir / "deploy.sh"
        deploy_script.write_text("#!/bin/bash\necho 'Deployed'\nexit 0\n")
        deploy_script.chmod(0o755)

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
def lead_agent(test_db, temp_git_repo):
    """Create LeadAgent instance with git repo."""
    repo_path, repo = temp_git_repo

    # Create project with workspace_path (fixed: per migration 002, root_path was replaced with workspace_path)
    project_id = test_db.create_project("test_project", "Test Project project")
    test_db.update_project(project_id, {"workspace_path": str(repo_path)})

    # Mock API key for LeadAgent
    api_key = os.environ.get("ANTHROPIC_API_KEY", "test-key")

    agent = LeadAgent(project_id, test_db, api_key=api_key)

    return agent


class TestLeadAgentStartIssueWork:
    """Test LeadAgent.start_issue_work() method."""

    def test_start_issue_work_creates_feature_branch(self, lead_agent, test_db):
        """Test that starting issue work creates a feature branch."""
        # Create an issue
        issue = Issue(
            project_id=lead_agent.project_id,
            issue_number="2.1",
            title="User Authentication",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
        )
        issue_id = test_db.create_issue(issue)

        # Start work on the issue
        result = lead_agent.start_issue_work(issue_id)

        # Verify result structure
        assert "branch_name" in result
        assert "issue_number" in result
        assert "status" in result

        # Verify branch was created
        assert result["status"] == "created"
        assert result["issue_number"] == "2.1"
        assert result["branch_name"] == "issue-2.1-user-authentication"

        # Verify database record
        branch_record = test_db.get_branch_for_issue(issue_id)
        assert branch_record is not None
        assert branch_record["branch_name"] == "issue-2.1-user-authentication"
        assert branch_record["status"] == "active"

    def test_start_issue_work_with_nonexistent_issue(self, lead_agent):
        """Test starting work on nonexistent issue raises ValueError."""
        with pytest.raises(ValueError, match="Issue .* not found"):
            lead_agent.start_issue_work(99999)

    def test_start_issue_work_with_existing_active_branch(self, lead_agent, test_db):
        """Test starting work on issue with active branch raises ValueError."""
        # Create issue
        issue = Issue(
            project_id=lead_agent.project_id,
            issue_number="2.1",
            title="User Auth",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
        )
        issue_id = test_db.create_issue(issue)

        # Start work once (creates branch)
        lead_agent.start_issue_work(issue_id)

        # Try to start work again
        with pytest.raises(ValueError, match="already has an active branch"):
            lead_agent.start_issue_work(issue_id)

    def test_start_issue_work_returns_correct_structure(self, lead_agent, test_db):
        """Test that start_issue_work returns correct data structure."""
        # Create issue
        issue = Issue(
            project_id=lead_agent.project_id,
            issue_number="3.5",
            title="Add Profile Settings",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=1,
        )
        issue_id = test_db.create_issue(issue)

        result = lead_agent.start_issue_work(issue_id)

        # Verify all required fields
        assert result["branch_name"] == "issue-3.5-add-profile-settings"
        assert result["issue_number"] == "3.5"
        assert result["status"] == "created"
        assert isinstance(result, dict)
        assert len(result) == 3  # Exactly 3 fields

    def test_start_issue_work_git_branch_created_in_repo(self, lead_agent, test_db, temp_git_repo):
        """Test that git branch is actually created in repository."""
        repo_path, repo = temp_git_repo

        # Create issue
        issue = Issue(
            project_id=lead_agent.project_id,
            issue_number="2.1",
            title="Test Feature",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
        )
        issue_id = test_db.create_issue(issue)

        # Start work
        result = lead_agent.start_issue_work(issue_id)

        # Verify git branch exists
        branch_name = result["branch_name"]
        assert branch_name in [b.name for b in repo.branches]


class TestLeadAgentCompleteIssue:
    """Test LeadAgent.complete_issue() method."""

    @pytest.mark.asyncio
    async def test_complete_issue_merges_when_all_tasks_done(self, lead_agent, test_db, temp_git_repo):
        """Test completing issue merges branch to main."""
        repo_path, repo = temp_git_repo

        # Create issue with completed tasks
        issue = Issue(
            project_id=lead_agent.project_id,
            issue_number="2.1",
            title="User Auth",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            workflow_step=1,
        )
        issue_id = test_db.create_issue(issue)

        # Create completed tasks
        test_db.create_task_with_issue(
            project_id=lead_agent.project_id,
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

        # Start work (creates branch)
        start_result = lead_agent.start_issue_work(issue_id)
        branch_name = start_result["branch_name"]

        # Make a commit on feature branch
        repo.git.checkout(branch_name)
        test_file = repo_path / "feature.txt"
        test_file.write_text("Feature implementation")
        repo.index.add(["feature.txt"])
        repo.index.commit("Implement feature")
        repo.git.checkout("main")

        # Complete issue
        result = await lead_agent.complete_issue(issue_id)

        # Verify result structure
        assert "merge_commit" in result
        assert "branch_name" in result
        assert "tasks_completed" in result
        assert "status" in result
        assert "deployment" in result

        assert result["status"] == "merged"
        assert result["branch_name"] == branch_name
        assert result["tasks_completed"] == 1
        assert len(result["merge_commit"]) == 40  # Git SHA length

        # Verify deployment was triggered
        assert result["deployment"]["status"] in ["success", "failed"]
        assert result["deployment"]["commit_hash"] == result["merge_commit"]

        # Verify merge actually happened
        assert (repo_path / "feature.txt").exists()

    @pytest.mark.asyncio
    async def test_complete_issue_fails_when_tasks_incomplete(self, lead_agent, test_db):
        """Test completing issue fails if tasks not done."""
        # Create issue with incomplete task
        issue = Issue(
            project_id=lead_agent.project_id,
            issue_number="2.1",
            title="User Auth",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            workflow_step=1,
        )
        issue_id = test_db.create_issue(issue)

        # Create incomplete task
        test_db.create_task_with_issue(
            project_id=lead_agent.project_id,
            issue_id=issue_id,
            task_number="2.1.1",
            parent_issue_number="2.1",
            title="Task 1",
            description="Test",
            status=TaskStatus.PENDING,  # NOT COMPLETED
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        # Start work
        lead_agent.start_issue_work(issue_id)

        # Try to complete
        with pytest.raises(ValueError, match="incomplete tasks"):
            await lead_agent.complete_issue(issue_id)

    @pytest.mark.asyncio
    async def test_complete_issue_fails_without_active_branch(self, lead_agent, test_db):
        """Test completing issue fails if no active branch."""
        # Create issue with completed tasks but no branch
        issue = Issue(
            project_id=lead_agent.project_id,
            issue_number="2.1",
            title="Test",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            workflow_step=1,
        )
        issue_id = test_db.create_issue(issue)

        # Create completed task
        test_db.create_task_with_issue(
            project_id=lead_agent.project_id,
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

        # Try to complete without starting work first
        with pytest.raises(ValueError, match="No active branch"):
            await lead_agent.complete_issue(issue_id)

    @pytest.mark.asyncio
    async def test_complete_issue_updates_database(self, lead_agent, test_db, temp_git_repo):
        """Test that completing issue updates database."""
        repo_path, repo = temp_git_repo

        # Create and complete issue
        issue = Issue(
            project_id=lead_agent.project_id,
            issue_number="2.1",
            title="Test",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            workflow_step=1,
        )
        issue_id = test_db.create_issue(issue)

        test_db.create_task_with_issue(
            project_id=lead_agent.project_id,
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

        # Start work
        start_result = lead_agent.start_issue_work(issue_id)
        branch_name = start_result["branch_name"]

        # Make commit
        repo.git.checkout(branch_name)
        (repo_path / "test.txt").write_text("test")
        repo.index.add(["test.txt"])
        repo.index.commit("Test commit")
        repo.git.checkout("main")

        # Complete issue
        result = await lead_agent.complete_issue(issue_id)

        # Verify database updated
        branches = test_db.get_all_branches_for_issue(issue_id)
        assert len(branches) > 0
        branch_record = branches[-1]
        assert branch_record["status"] == "merged"
        assert branch_record["merge_commit"] == result["merge_commit"]

        # Verify issue status updated
        updated_issue = test_db.get_issue(issue_id)
        assert updated_issue.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_complete_issue_nonexistent_issue(self, lead_agent):
        """Test completing nonexistent issue raises ValueError."""
        with pytest.raises(ValueError, match="Issue .* not found"):
            await lead_agent.complete_issue(99999)

    @pytest.mark.asyncio
    async def test_complete_issue_with_multiple_completed_tasks(self, lead_agent, test_db, temp_git_repo):
        """Test completing issue counts all completed tasks."""
        repo_path, repo = temp_git_repo

        # Create issue with multiple completed tasks
        issue = Issue(
            project_id=lead_agent.project_id,
            issue_number="2.1",
            title="Multi-task Feature",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            workflow_step=1,
        )
        issue_id = test_db.create_issue(issue)

        # Create 3 completed tasks
        for i in range(3):
            test_db.create_task_with_issue(
                project_id=lead_agent.project_id,
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

        # Start and complete
        start_result = lead_agent.start_issue_work(issue_id)
        branch_name = start_result["branch_name"]

        repo.git.checkout(branch_name)
        (repo_path / "feature.txt").write_text("feature")
        repo.index.add(["feature.txt"])
        repo.index.commit("Feature commit")
        repo.git.checkout("main")

        result = await lead_agent.complete_issue(issue_id)

        # Verify task count
        assert result["tasks_completed"] == 3


class TestLeadAgentGitWorkflowIntegration:
    """Integration tests for end-to-end git workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow_start_to_merge(self, lead_agent, test_db, temp_git_repo):
        """Test complete workflow: create issue → start work → complete → merge."""
        repo_path, repo = temp_git_repo

        # 1. Create issue
        issue = Issue(
            project_id=lead_agent.project_id,
            issue_number="1.1",
            title="Authentication System",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
        )
        issue_id = test_db.create_issue(issue)

        # 2. Add tasks
        test_db.create_task_with_issue(
            project_id=lead_agent.project_id,
            issue_id=issue_id,
            task_number="1.1.1",
            parent_issue_number="1.1",
            title="Implement login",
            description="Login functionality",
            status=TaskStatus.COMPLETED,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        # 3. Start work
        start_result = lead_agent.start_issue_work(issue_id)
        assert start_result["status"] == "created"
        branch_name = start_result["branch_name"]

        # 4. Simulate development work
        repo.git.checkout(branch_name)
        auth_file = repo_path / "auth.py"
        auth_file.write_text("def login(): pass")
        repo.index.add(["auth.py"])
        repo.index.commit("Add login functionality")
        repo.git.checkout("main")

        # 5. Complete issue
        complete_result = await lead_agent.complete_issue(issue_id)
        assert complete_result["status"] == "merged"
        assert complete_result["tasks_completed"] == 1

        # 6. Verify final state
        assert (repo_path / "auth.py").exists()
        updated_issue = test_db.get_issue(issue_id)
        assert updated_issue.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_workflow_with_no_tasks_fails(self, lead_agent, test_db):
        """Test workflow fails if issue has no tasks."""
        # Create issue without tasks
        issue = Issue(
            project_id=lead_agent.project_id,
            issue_number="2.1",
            title="Empty Issue",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
        )
        issue_id = test_db.create_issue(issue)

        # Start work should succeed
        lead_agent.start_issue_work(issue_id)

        # Complete should fail (no tasks)
        with pytest.raises(ValueError, match="incomplete tasks"):
            await lead_agent.complete_issue(issue_id)

    def test_multiple_issues_separate_branches(self, lead_agent, test_db, temp_git_repo):
        """Test that multiple issues create separate branches."""
        repo_path, repo = temp_git_repo

        # Create two issues
        issue1_id = test_db.create_issue(
            Issue(
                project_id=lead_agent.project_id,
                issue_number="1.1",
                title="Feature A",
                status=TaskStatus.PENDING,
                priority=0,
                workflow_step=1,
            )
        )

        issue2_id = test_db.create_issue(
            Issue(
                project_id=lead_agent.project_id,
                issue_number="1.2",
                title="Feature B",
                status=TaskStatus.PENDING,
                priority=0,
                workflow_step=1,
            )
        )

        # Start work on both
        result1 = lead_agent.start_issue_work(issue1_id)
        result2 = lead_agent.start_issue_work(issue2_id)

        # Verify separate branches
        assert result1["branch_name"] == "issue-1.1-feature-a"
        assert result2["branch_name"] == "issue-1.2-feature-b"
        assert result1["branch_name"] != result2["branch_name"]

        # Verify both branches exist in git
        branch_names = [b.name for b in repo.branches]
        assert result1["branch_name"] in branch_names
        assert result2["branch_name"] in branch_names
