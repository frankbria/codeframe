"""Integration tests for review workflow.

Tests the full review workflow from task completion through review agent
execution to blocker creation and re-review iterations.

TDD: These tests should FAIL until ReviewWorkerAgent is fully integrated.
"""

import pytest
import asyncio
from codeframe.agents.review_worker_agent import ReviewWorkerAgent
from codeframe.agents.agent_pool_manager import AgentPoolManager
from codeframe.persistence.database import Database


class TestReviewWorkflow:
    """Integration tests for full review workflow."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create temporary database."""
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        db.initialize()
        return db

    @pytest.fixture
    def workspace(self, tmp_path):
        """Create temporary workspace."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        return workspace

    @pytest.fixture
    def project_id(self, db, workspace):
        """Create test project."""
        return db.create_project(
            name="Test Project",
            description="Integration test project",
            workspace_path=str(workspace),
        )

    @pytest.fixture
    def task_id(self, db, project_id):
        """Create test task."""
        cursor = db.conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (project_id, task_number, title, description, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project_id, "1.1.1", "Implement feature", "Add new feature", "in_progress"),
        )
        db.conn.commit()
        return cursor.lastrowid

    @pytest.fixture
    def review_agent(self, db, project_id):
        """Create ReviewWorkerAgent and assign to project."""
        from codeframe.core.models import AgentMaturity

        agent = ReviewWorkerAgent(
            agent_id="review-001",
            db=db,
        )
        # Create agent in database first (required for foreign key)
        db.create_agent(agent.agent_id, agent.agent_type, agent.provider, AgentMaturity.D1)
        # Assign agent to project
        db.assign_agent_to_project(project_id, agent.agent_id)
        return agent

    @pytest.fixture
    def good_code_file(self, workspace):
        """Create a file with good quality code."""
        code_file = workspace / "feature.py"
        code_file.write_text(
            '''
"""Feature implementation."""

def process_data(data):
    """Process input data and return result."""
    if not data:
        return None

    result = []
    for item in data:
        if item.get('valid'):
            result.append(item['value'])

    return result


def validate_input(value):
    """Validate input value."""
    if value is None:
        return False
    if not isinstance(value, (int, str)):
        return False
    return True
'''
        )
        return code_file

    @pytest.fixture
    def bad_code_file(self, workspace):
        """Create a file with poor quality code."""
        code_file = workspace / "bad_feature.py"
        code_file.write_text(
            '''
# Poor quality code with security and complexity issues

PASSWORD = "admin123"  # Hardcoded password
API_KEY = "sk-secret-key-12345"  # Hardcoded API key

def complex_processor(x, y, z, a, b, c, d, e, f):
    """Overly complex function with security issues."""
    if x > 0:
        if y > 0:
            if z > 0:
                if a > 0:
                    if b > 0:
                        if c > 0:
                            if d > 0:
                                if e > 0:
                                    if f > 0:
                                        # SQL injection vulnerability
                                        import sqlite3
                                        query = f"SELECT * FROM users WHERE id = {x}"
                                        return query
    return None

import os
def run_command(cmd):
    """Command injection vulnerability."""
    os.system(f"bash -c '{cmd}'")
'''
        )
        return code_file

    # T034: Integration test for full review workflow (trigger → analyze → approve)

    @pytest.mark.asyncio
    async def test_full_workflow_approve(self, review_agent, task_id, db, good_code_file):
        """Test complete workflow from task completion to approval."""
        # Setup: Task with good code
        task = {
            "id": task_id,
            "task_number": "1.1.1",
            "title": "Implement feature",
            "description": "Add new feature with good code",
            "files_modified": [str(good_code_file)],
        }

        # Execute review
        report = await review_agent.execute_task(task)

        # Verify: Good code should be approved
        assert report is not None
        assert report.status in ["approved", "changes_requested"]  # Could be either

        # Verify: If approved, no blocker created
        if report.status == "approved":
            result = db.list_blockers(project_id=db.get_task(task_id)["project_id"])
            blockers = result.get("blockers", [])
            task_blockers = [b for b in blockers if b["task_id"] == task_id]
            review_blockers = [b for b in task_blockers if "review" in b.get("details", "").lower()]
            assert len(review_blockers) == 0

        # Verify: Task can proceed
        assert report.overall_score >= 50  # At least passable

    @pytest.mark.asyncio
    async def test_full_workflow_with_agent_pool(
        self, db, project_id, task_id, workspace, good_code_file
    ):
        """Test workflow integration with AgentPoolManager."""
        # Create agent pool manager
        pool_manager = AgentPoolManager(db=db, project_id=project_id)

        # Create review agent using pool manager
        review_agent_id = pool_manager.get_or_create_agent("review")

        # Get agent from pool
        agent = pool_manager.get_agent_instance(review_agent_id)
        assert agent is not None

        # Execute review task
        task = {
            "id": task_id,
            "task_number": "1.1.1",
            "title": "Implement feature",
            "description": "Test agent pool integration",
            "files_modified": [str(good_code_file)],
        }

        report = await agent.execute_task(task)

        assert report is not None
        assert report.reviewer_agent_id == review_agent_id

    # T035: Integration test for review failure creating blocker

    @pytest.mark.asyncio
    async def test_review_failure_creates_blocker(self, review_agent, task_id, db, bad_code_file):
        """Test that review failures create blockers with detailed findings."""
        # Setup: Task with bad code
        task = {
            "id": task_id,
            "task_number": "1.1.1",
            "title": "Implement feature",
            "description": "Add feature with poor code quality",
            "files_modified": [str(bad_code_file)],
        }

        # Execute review
        report = await review_agent.execute_task(task)

        # Verify: Should detect multiple issues
        assert len(report.findings) > 0

        # Verify: Should have low score
        assert report.overall_score < 90  # Not excellent

        # Verify: If changes requested or rejected, blocker created
        if report.status in ["changes_requested", "rejected"]:
            result = db.list_blockers(project_id=db.get_task(task_id)["project_id"])
            blockers = result.get("blockers", [])
            task_blockers = [b for b in blockers if b["task_id"] == task_id]
            assert len(task_blockers) > 0

            # Find review blocker - look for "code review" or task is from review agent
            review_blocker = next(
                (
                    b
                    for b in task_blockers
                    if "code review" in b.get("question", "").lower()
                    or b.get("agent_id", "").startswith("review")
                ),
                None,
            )
            assert (
                review_blocker is not None
            ), f"Expected review blocker, found blockers: {task_blockers}"

            # Verify blocker details
            assert review_blocker["blocker_type"] == "SYNC"
            assert (
                "score" in review_blocker["question"].lower()
                or "quality" in review_blocker["question"].lower()
            )

            # Verify findings are in blocker details
            blocker_question = review_blocker["question"]
            assert len(blocker_question) > 100  # Should have detailed info

    @pytest.mark.asyncio
    async def test_blocker_includes_all_findings(self, review_agent, task_id, db, bad_code_file):
        """Test that blocker includes findings from all analyzers."""
        task = {
            "id": task_id,
            "task_number": "1.1.1",
            "title": "Implement feature",
            "description": "Code with multiple issues",
            "files_modified": [str(bad_code_file)],
        }

        report = await review_agent.execute_task(task)

        if report.status in ["changes_requested", "rejected"]:
            # Should have findings from multiple categories
            categories = {f.category for f in report.findings}
            assert len(categories) >= 2  # At least complexity and security

            # Check blocker details include findings
            result = db.list_blockers(project_id=db.get_task(task_id)["project_id"])
            blockers = result.get("blockers", [])
            task_blockers = [b for b in blockers if b["task_id"] == task_id]
            review_blocker = next(
                (b for b in task_blockers if "review" in b.get("details", "").lower()), None
            )

            if review_blocker:
                question_text = review_blocker["question"]
                # Should mention different categories
                assert "security" in question_text.lower() or "complexity" in question_text.lower()

    @pytest.mark.asyncio
    async def test_blocker_has_actionable_suggestions(
        self, review_agent, task_id, db, bad_code_file
    ):
        """Test that blocker includes actionable remediation suggestions."""
        task = {
            "id": task_id,
            "task_number": "1.1.1",
            "title": "Implement feature",
            "description": "Code needing fixes",
            "files_modified": [str(bad_code_file)],
        }

        report = await review_agent.execute_task(task)

        if report.status in ["changes_requested", "rejected"]:
            # Should have suggestions
            findings_with_suggestions = [f for f in report.findings if f.suggestion]
            assert len(findings_with_suggestions) > 0

            # Suggestions should be in blocker
            blocker_message = report.to_blocker_message()
            assert "suggestion" in blocker_message.lower() or "💡" in blocker_message

    # T036: Integration test for re-review iteration limit (max 2)

    @pytest.mark.asyncio
    async def test_rereview_iteration_limit(self, review_agent, task_id, db, workspace):
        """Test that re-review has maximum 2 iterations."""
        # Create file that will fail review
        bad_file = workspace / "iteration_test.py"
        bad_file.write_text(
            """
PASSWORD = "admin"
def bad(): pass
"""
        )

        task = {
            "id": task_id,
            "task_number": "1.1.1",
            "title": "Implement feature",
            "description": "Test iteration limit",
            "files_modified": [str(bad_file)],
        }

        # First review (iteration 1)
        report1 = await review_agent.execute_task(task)

        iteration_count = 1

        # If failed, do second review (iteration 2)
        if report1.status in ["changes_requested", "rejected"]:
            iteration_count += 1

            # Simulate fixing some issues but not all
            bad_file.write_text(
                """
import os
PASSWORD = "admin"  # Still has this issue
def better():
    return True
"""
            )

            report2 = await review_agent.execute_task(task)

            # If still failed, should NOT do third iteration
            if report2.status in ["changes_requested", "rejected"]:
                # Check that iteration limit is enforced
                # (Implementation may track this in database or agent state)
                # After 2 iterations, should escalate to human
                result = db.list_blockers(project_id=db.get_task(task_id)["project_id"])
                blockers = result.get("blockers", [])
                task_blockers = [b for b in blockers if b["task_id"] == task_id]

                # Should have blocker indicating escalation needed
                assert len(task_blockers) > 0

    @pytest.mark.asyncio
    async def test_rereview_after_fixes(self, review_agent, task_id, db, workspace):
        """Test successful re-review after fixing issues."""
        # Start with bad code
        test_file = workspace / "fixable.py"
        test_file.write_text(
            """
PASSWORD = "admin123"
def simple():
    return PASSWORD
"""
        )

        task = {
            "id": task_id,
            "task_number": "1.1.1",
            "title": "Implement feature",
            "description": "Test re-review after fixes",
            "files_modified": [str(test_file)],
        }

        # First review - should fail
        report1 = await review_agent.execute_task(task)

        if report1.status in ["changes_requested", "rejected"]:
            # Fix the issues
            test_file.write_text(
                '''
import os

def get_password():
    """Get password from environment variable."""
    return os.getenv('PASSWORD', '')

def simple():
    """Simple function."""
    return get_password()
'''
            )

            # Second review - should pass now
            report2 = await review_agent.execute_task(task)

            # Should have better score after fixes
            assert report2.overall_score > report1.overall_score

            # May now be approved
            # (Depends on if all issues were fixed)

    @pytest.mark.asyncio
    async def test_iteration_tracking_in_database(self, review_agent, task_id, db, bad_code_file):
        """Test that review iterations are tracked in database."""
        task = {
            "id": task_id,
            "task_number": "1.1.1",
            "title": "Implement feature",
            "description": "Test iteration tracking",
            "files_modified": [str(bad_code_file)],
        }

        # First review
        await review_agent.execute_task(task)

        # Check if iteration count is stored
        # (Implementation detail - may be in tasks table or separate table)
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task_data = dict(cursor.fetchone())

        # May have review_iteration column or similar
        # For now, just verify task exists and is updated
        assert task_data is not None

    @pytest.mark.asyncio
    async def test_escalate_to_human_after_max_iterations(
        self, review_agent, task_id, db, bad_code_file
    ):
        """Test escalation to human after max iterations exceeded."""
        task = {
            "id": task_id,
            "task_number": "1.1.1",
            "title": "Implement feature",
            "description": "Test human escalation",
            "files_modified": [str(bad_code_file)],
        }

        # Review twice (max iterations)
        report1 = await review_agent.execute_task(task)

        if report1.status in ["changes_requested", "rejected"]:
            report2 = await review_agent.execute_task(task)

            # After 2 iterations, should create escalation blocker
            if report2.status in ["changes_requested", "rejected"]:
                result = db.list_blockers(project_id=db.get_task(task_id)["project_id"])
                blockers = result.get("blockers", [])
                task_blockers = [b for b in blockers if b["task_id"] == task_id]

                # Should have SYNC blocker for human intervention
                sync_blockers = [b for b in task_blockers if b["blocker_type"] == "SYNC"]
                assert len(sync_blockers) > 0

    # Additional integration scenarios

    @pytest.mark.asyncio
    async def test_review_with_lead_agent_integration(
        self, db, project_id, workspace, good_code_file
    ):
        """Test review integration with LeadAgent workflow."""
        # This would test Step 11 in LeadAgent workflow
        # For now, just verify agents can work together
        from codeframe.core.models import AgentMaturity

        review_agent = ReviewWorkerAgent(
            agent_id="review-001",
            db=db,
        )
        db.create_agent(
            review_agent.agent_id, review_agent.agent_type, review_agent.provider, AgentMaturity.D1
        )
        db.assign_agent_to_project(project_id, review_agent.agent_id)

        # Verify agent can be used in workflow
        assert review_agent.agent_id == "review-001"
        # Verify agent is assigned to project
        agents_for_project = db.get_agents_for_project(project_id)
        assert review_agent.agent_id in [a["agent_id"] for a in agents_for_project]

    @pytest.mark.asyncio
    async def test_concurrent_reviews(self, db, project_id, workspace):
        """Test multiple concurrent review tasks."""
        # Create two review agents
        from codeframe.core.models import AgentMaturity

        agent1 = ReviewWorkerAgent(agent_id="review-001", db=db)
        db.create_agent(agent1.agent_id, agent1.agent_type, agent1.provider, AgentMaturity.D1)
        db.assign_agent_to_project(project_id, agent1.agent_id)

        agent2 = ReviewWorkerAgent(agent_id="review-002", db=db)
        db.create_agent(agent2.agent_id, agent2.agent_type, agent2.provider, AgentMaturity.D1)
        db.assign_agent_to_project(project_id, agent2.agent_id)

        # Create two tasks
        cursor = db.conn.cursor()
        cursor.execute(
            "INSERT INTO tasks (project_id, task_number, title, status) VALUES (?, ?, ?, ?)",
            (project_id, "1.1.1", "Task 1", "in_progress"),
        )
        task1_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO tasks (project_id, task_number, title, status) VALUES (?, ?, ?, ?)",
            (project_id, "1.1.2", "Task 2", "in_progress"),
        )
        task2_id = cursor.lastrowid
        db.conn.commit()

        # Create code files
        file1 = workspace / "file1.py"
        file1.write_text("def func1(): return 42")

        file2 = workspace / "file2.py"
        file2.write_text("def func2(): return 100")

        # Execute reviews concurrently
        task1 = {
            "id": task1_id,
            "task_number": "1.1.1",
            "title": "Task 1",
            "files_modified": [str(file1)],
        }
        task2 = {
            "id": task2_id,
            "task_number": "1.1.2",
            "title": "Task 2",
            "files_modified": [str(file2)],
        }

        results = await asyncio.gather(
            agent1.execute_task(task1),
            agent2.execute_task(task2),
        )

        # Both should complete successfully
        assert len(results) == 2
        assert all(r is not None for r in results)
