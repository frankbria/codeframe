"""Tests for Lead Agent blocker handling (T036, T037).

Following TDD: These tests are written FIRST, before implementation.

User Story 4 - SYNC vs ASYNC Blocker Handling (Priority: P2)
T036: Add SYNC blocker dependency handling to LeadAgent (pause dependent tasks)
T037: Add ASYNC blocker handling to LeadAgent (allow independent work to continue)
"""

import pytest
from unittest.mock import MagicMock, patch
from codeframe.agents.lead_agent import LeadAgent
from codeframe.persistence.database import Database
from codeframe.core.models import BlockerType, TaskStatus, Issue


@pytest.mark.unit
class TestLeadAgentSyncBlockerHandling:
    """Test SYNC blocker dependency handling (T036)."""

    def _create_test_task(
        self,
        db,
        project_id,
        issue_id,
        task_number,
        title,
        status=TaskStatus.PENDING,
        depends_on=None,
    ):
        """Helper to create a test task."""
        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number=task_number,
            parent_issue_number="1.0",
            title=title,
            description=f"Description for {title}",
            status=status,
            priority=1,
            workflow_step=1,
            can_parallelize=False,
            requires_mcp=False,
        )

        if depends_on:
            db.conn.execute("UPDATE tasks SET depends_on = ? WHERE id = ?", (depends_on, task_id))
            db.conn.commit()

        return task_id

    @pytest.mark.asyncio
    async def test_sync_blocker_pauses_dependent_tasks(self, temp_db_path):
        """Test that SYNC blocker pauses dependent tasks.

        Scenario:
        1. Task A is running
        2. Task A creates SYNC blocker
        3. Task B depends on Task A
        4. Verify Task B is NOT assigned while blocker is PENDING
        5. Resolve blocker
        6. Verify Task B can now be assigned
        """
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test project description")

        # Create an issue first
        issue = Issue(
            project_id=project_id,
            issue_number="1.0",
            title="Test Issue",
            description="Test issue for blocker handling",
            priority=1,
            workflow_step=1,
        )
        issue_id = db.create_issue(issue)

        # Create Task A and Task B
        task_a_id = self._create_test_task(
            db, project_id, issue_id, "1.1", "Implement auth", TaskStatus.IN_PROGRESS
        )
        task_b_id = self._create_test_task(
            db,
            project_id,
            issue_id,
            "1.2",
            "Add user profile",
            TaskStatus.PENDING,
            depends_on=str(task_a_id),
        )

        # Create SYNC blocker for Task A
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=task_a_id,
            blocker_type=BlockerType.SYNC,
            question="Should we use JWT or session-based auth?",
        )

        # ACT
        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # Check if Task B can be assigned (should be blocked)
        can_assign_b = await agent.can_assign_task(task_b_id)

        # ASSERT
        assert can_assign_b is False, "Task B should be blocked by SYNC blocker on Task A"

        # Resolve the blocker
        db.resolve_blocker(blocker_id, "Use JWT for stateless auth")

        # ACT - check again after resolution
        can_assign_b_after = await agent.can_assign_task(task_b_id)

        # ASSERT
        assert can_assign_b_after is True, "Task B should be assignable after blocker resolved"

    @pytest.mark.asyncio
    async def test_sync_blocker_blocks_all_dependent_tasks(self, temp_db_path):
        """Test that SYNC blocker blocks ALL tasks that depend on blocked task.

        Scenario:
        1. Task A creates SYNC blocker
        2. Tasks B, C, D all depend on Task A (directly or transitively)
        3. Verify ALL dependent tasks are blocked
        """
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test project description")

        # Create issue
        issue = Issue(
            project_id=project_id,
            issue_number="1.0",
            title="Test Issue",
            description="Test issue for blocker handling",
            priority=1,
            workflow_step=1,
        )
        issue_id = db.create_issue(issue)

        # Create tasks with dependencies
        task_a_id = self._create_test_task(
            db, project_id, issue_id, "1.1", "Setup database", TaskStatus.IN_PROGRESS
        )
        task_b_id = self._create_test_task(
            db,
            project_id,
            issue_id,
            "1.2",
            "Add users table",
            TaskStatus.PENDING,
            depends_on=str(task_a_id),
        )
        task_c_id = self._create_test_task(
            db,
            project_id,
            issue_id,
            "1.3",
            "Add user migration",
            TaskStatus.PENDING,
            depends_on=str(task_b_id),
        )
        task_d_id = self._create_test_task(
            db,
            project_id,
            issue_id,
            "1.4",
            "Add sessions table",
            TaskStatus.PENDING,
            depends_on=str(task_a_id),
        )

        # Create SYNC blocker for Task A
        db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=task_a_id,
            blocker_type=BlockerType.SYNC,
            question="Which database should we use?",
        )

        # ACT
        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        can_assign_b = await agent.can_assign_task(task_b_id)
        can_assign_c = await agent.can_assign_task(task_c_id)
        can_assign_d = await agent.can_assign_task(task_d_id)

        # ASSERT
        assert can_assign_b is False, "Task B should be blocked (direct dependency)"
        assert can_assign_c is False, "Task C should be blocked (transitive dependency)"
        assert can_assign_d is False, "Task D should be blocked (direct dependency)"

    @pytest.mark.asyncio
    async def test_sync_blocker_does_not_block_independent_tasks(self, temp_db_path):
        """Test that SYNC blocker only blocks dependent tasks, not independent ones.

        Scenario:
        1. Task A creates SYNC blocker
        2. Task B depends on Task A (should be blocked)
        3. Task C is independent (should NOT be blocked)
        4. Verify Task C can still be assigned
        """
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test project description")

        # Create issue
        issue = Issue(
            project_id=project_id,
            issue_number="1.0",
            title="Test Issue",
            description="Test issue for blocker handling",
            priority=1,
            workflow_step=1,
        )
        issue_id = db.create_issue(issue)

        # Create tasks
        task_a_id = self._create_test_task(
            db, project_id, issue_id, "1.1", "Backend auth", TaskStatus.IN_PROGRESS
        )
        task_b_id = self._create_test_task(
            db,
            project_id,
            issue_id,
            "1.2",
            "User profile",
            TaskStatus.PENDING,
            depends_on=str(task_a_id),
        )
        task_c_id = self._create_test_task(
            db, project_id, issue_id, "2.1", "Frontend styling", TaskStatus.PENDING
        )

        # Create SYNC blocker for Task A
        db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=task_a_id,
            blocker_type=BlockerType.SYNC,
            question="JWT or session auth?",
        )

        # ACT
        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        can_assign_b = await agent.can_assign_task(task_b_id)
        can_assign_c = await agent.can_assign_task(task_c_id)

        # ASSERT
        assert can_assign_b is False, "Task B should be blocked (depends on A)"
        assert can_assign_c is True, "Task C should NOT be blocked (independent)"


@pytest.mark.unit
class TestLeadAgentAsyncBlockerHandling:
    """Test ASYNC blocker handling (T037)."""

    def _create_test_task(
        self,
        db,
        project_id,
        issue_id,
        task_number,
        title,
        status=TaskStatus.PENDING,
        depends_on=None,
    ):
        """Helper to create a test task."""
        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number=task_number,
            parent_issue_number="1.0",
            title=title,
            description=f"Description for {title}",
            status=status,
            priority=1,
            workflow_step=1,
            can_parallelize=False,
            requires_mcp=False,
        )

        if depends_on:
            db.conn.execute("UPDATE tasks SET depends_on = ? WHERE id = ?", (depends_on, task_id))
            db.conn.commit()

        return task_id

    @pytest.mark.asyncio
    async def test_async_blocker_allows_dependent_tasks_to_continue(self, temp_db_path):
        """Test that ASYNC blocker allows dependent tasks to continue.

        Scenario:
        1. Task A creates ASYNC blocker (informational question)
        2. Task B depends on Task A
        3. Verify Task B CAN still be assigned (ASYNC doesn't block)
        """
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test project description")

        # Create issue
        issue = Issue(
            project_id=project_id,
            issue_number="1.0",
            title="Test Issue",
            description="Test issue for blocker handling",
            priority=1,
            workflow_step=1,
        )
        issue_id = db.create_issue(issue)

        # Create tasks
        task_a_id = self._create_test_task(
            db, project_id, issue_id, "1.1", "Implement search", TaskStatus.IN_PROGRESS
        )
        task_b_id = self._create_test_task(
            db,
            project_id,
            issue_id,
            "1.2",
            "Add search filters",
            TaskStatus.PENDING,
            depends_on=str(task_a_id),
        )

        # Create ASYNC blocker for Task A (informational question)
        db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=task_a_id,
            blocker_type=BlockerType.ASYNC,
            question="Do you prefer full-text search or simple keyword matching?",
        )

        # ACT
        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        can_assign_b = await agent.can_assign_task(task_b_id)

        # ASSERT
        assert can_assign_b is True, "Task B should NOT be blocked by ASYNC blocker"

    @pytest.mark.asyncio
    async def test_async_blocker_allows_all_work_to_continue(self, temp_db_path):
        """Test that ASYNC blocker doesn't block any tasks.

        Scenario:
        1. Task A creates ASYNC blocker
        2. Multiple tasks depend on Task A
        3. Verify all tasks can continue (ASYNC is informational only)
        """
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test project description")

        # Create issue
        issue = Issue(
            project_id=project_id,
            issue_number="1.0",
            title="Test Issue",
            description="Test issue for blocker handling",
            priority=1,
            workflow_step=1,
        )
        issue_id = db.create_issue(issue)

        # Create tasks
        task_a_id = self._create_test_task(
            db, project_id, issue_id, "1.1", "Implement API endpoint", TaskStatus.IN_PROGRESS
        )
        task_b_id = self._create_test_task(
            db,
            project_id,
            issue_id,
            "1.2",
            "Add API tests",
            TaskStatus.PENDING,
            depends_on=str(task_a_id),
        )
        task_c_id = self._create_test_task(
            db,
            project_id,
            issue_id,
            "1.3",
            "Add API docs",
            TaskStatus.PENDING,
            depends_on=str(task_a_id),
        )

        # Create ASYNC blocker for Task A
        db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=task_a_id,
            blocker_type=BlockerType.ASYNC,
            question="Should we add rate limiting to this endpoint?",
        )

        # ACT
        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        can_assign_b = await agent.can_assign_task(task_b_id)
        can_assign_c = await agent.can_assign_task(task_c_id)

        # ASSERT
        assert can_assign_b is True, "Task B should continue (ASYNC blocker)"
        assert can_assign_c is True, "Task C should continue (ASYNC blocker)"


@pytest.mark.integration
class TestLeadAgentBlockerHandlingIntegration:
    """Integration tests for blocker handling in multi-agent execution."""

    @pytest.mark.asyncio
    async def test_multi_agent_execution_pauses_for_sync_blocker(self, temp_db_path):
        """Test that multi-agent execution correctly pauses for SYNC blockers.

        Scenario:
        1. Start multi-agent execution with 3 tasks
        2. Task A creates SYNC blocker mid-execution
        3. Verify dependent Task B is not assigned
        4. Verify independent Task C continues
        5. Resolve blocker
        6. Verify Task B resumes
        """
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test project description")

        # Create issues first
        issue_1_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.0",
                "title": "Feature 1",
                "status": "pending",
                "priority": 0,
                "workflow_step": 1,
            }
        )

        issue_2_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "2.0",
                "title": "Feature 2",
                "status": "pending",
                "priority": 0,
                "workflow_step": 1,
            }
        )

        # Create task chain: A -> B (dependent), and C (independent)
        task_a_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_1_id,
            task_number="1.1",
            parent_issue_number="1.0",
            title="Task A",
            description="Will create SYNC blocker",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
            can_parallelize=True,
        )

        task_b_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_1_id,
            task_number="1.2",
            parent_issue_number="1.0",
            title="Task B",
            description="Depends on A",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
            can_parallelize=True,
        )
        # Set dependency (use JSON array format with task ID)
        db.conn.execute(
            "UPDATE tasks SET depends_on = ? WHERE id = ?", (f"[{task_a_id}]", task_b_id)
        )
        db.conn.commit()

        task_c_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_2_id,
            task_number="2.1",
            parent_issue_number="2.0",
            title="Task C",
            description="Independent task",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
            can_parallelize=True,
        )

        # ACT
        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # Mock agent execution to create blocker
        with (
            patch.object(agent.agent_pool_manager, "get_or_create_agent") as mock_get_agent,
            patch.object(agent.agent_pool_manager, "mark_agent_busy"),
            patch.object(agent.agent_pool_manager, "mark_agent_idle"),
            patch.object(agent.agent_pool_manager, "get_agent_instance") as mock_get_instance,
        ):

            # Mock worker agent that creates blocker for Task A
            mock_worker = MagicMock()

            async def mock_execute_task_a(task_dict):
                if task_dict["id"] == task_a_id:
                    # Create SYNC blocker during Task A execution
                    db.create_blocker(
                        agent_id="backend-worker-001",
                        project_id=1,
                        task_id=task_a_id,
                        blocker_type=BlockerType.SYNC,
                        question="Critical decision needed",
                    )
                    db.update_task(task_a_id, {"status": "blocked"})
                    raise Exception("Blocker created, task paused")
                else:
                    db.update_task(task_dict["id"], {"status": "completed"})

            mock_worker.execute_task = mock_execute_task_a
            mock_get_instance.return_value = mock_worker
            mock_get_agent.return_value = "backend-worker-001"

            # Execute (should handle blocker gracefully)
            try:
                _result = await agent.start_multi_agent_execution(timeout=10)
            except Exception:
                pass  # Expected - blocker will pause execution

            # ASSERT
            task_a = db.get_task(task_a_id)
            task_b = db.get_task(task_b_id)
            task_c = db.get_task(task_c_id)

            # Task A should be blocked
            assert task_a.status.value in [
                "blocked",
                "in_progress",
            ], "Task A should be blocked or in_progress"

            # Task B should NOT be started (dependent on blocked Task A)
            assert task_b.status.value == "pending", "Task B should remain pending (blocked by Task A)"

            # Task C should have completed (independent)
            assert task_c.status.value == "completed", "Task C should complete (independent)"
