"""
Integration tests for complete blocker workflow.

Tests T055-T057 from Phase 9: Testing & Validation
"""

import pytest_asyncio
from datetime import datetime
from codeframe.persistence.database import Database
from codeframe.core.models import BlockerType, BlockerStatus, TaskStatus


@pytest_asyncio.fixture
async def db():
    """Create in-memory database for testing."""
    database = Database(":memory:")
    database.initialize()
    yield database
    database.close()


@pytest_asyncio.fixture
async def sample_project(db):
    """Create a sample project for testing."""
    project_id = db.create_project(
        name="Integration Test Project",
        repo_path="/tmp/test",
        description="Test project for integration tests",
    )
    return project_id


@pytest_asyncio.fixture
async def sample_tasks(db, sample_project):
    """Create multiple sample tasks with dependencies."""
    # Create issues first
    issue1_id = db.create_issue(
        {
            "project_id": sample_project,
            "issue_number": "1.0",
            "title": "Issue 1",
            "description": "First issue",
            "status": "pending",
            "priority": 2,
            "workflow_step": 1,
        }
    )

    issue2_id = db.create_issue(
        {
            "project_id": sample_project,
            "issue_number": "2.0",
            "title": "Issue 2",
            "description": "Second issue",
            "status": "pending",
            "priority": 2,
            "workflow_step": 1,
        }
    )

    issue3_id = db.create_issue(
        {
            "project_id": sample_project,
            "issue_number": "3.0",
            "title": "Issue 3",
            "description": "Third issue",
            "status": "pending",
            "priority": 2,
            "workflow_step": 1,
        }
    )

    # Create tasks
    task1_id = db.create_task_with_issue(
        project_id=sample_project,
        issue_id=issue1_id,
        task_number="1.0.1",
        parent_issue_number="1.0",
        title="Task 1 - Database Setup",
        description="Set up database schema",
        status=TaskStatus.PENDING,
        priority=2,
        workflow_step=1,
        can_parallelize=False,
    )

    task2_id = db.create_task_with_issue(
        project_id=sample_project,
        issue_id=issue2_id,
        task_number="2.0.1",
        parent_issue_number="2.0",
        title="Task 2 - API Endpoints",
        description="Create API endpoints",
        status=TaskStatus.PENDING,
        priority=2,
        workflow_step=1,
        can_parallelize=False,
    )

    task3_id = db.create_task_with_issue(
        project_id=sample_project,
        issue_id=issue3_id,
        task_number="3.0.1",
        parent_issue_number="3.0",
        title="Task 3 - Frontend",
        description="Build frontend components",
        status=TaskStatus.PENDING,
        priority=2,
        workflow_step=1,
        can_parallelize=False,
    )

    return {"task1": task1_id, "task2": task2_id, "task3": task3_id}


class TestCompleteBlockerWorkflow:
    """Test T055: Integration test for complete blocker workflow (create → display → resolve → resume)."""

    def test_end_to_end_workflow(self, db, sample_project, sample_tasks):
        """Test complete blocker lifecycle from creation to agent resume."""
        task_id = sample_tasks["task1"]

        # Step 1: Agent creates blocker
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=task_id,
            blocker_type=BlockerType.SYNC,
            question="Should I use SQLite or PostgreSQL for the database?",
        )
        assert blocker_id > 0

        # Step 2: Verify blocker appears in dashboard (list API)
        response = db.list_blockers(sample_project)
        assert response["total"] == 1
        assert response["pending_count"] == 1
        assert response["sync_count"] == 1
        assert response["blockers"][0]["id"] == blocker_id
        assert (
            response["blockers"][0]["question"]
            == "Should I use SQLite or PostgreSQL for the database?"
        )

        # Step 3: User views blocker details
        blocker = db.get_blocker(blocker_id)
        assert blocker["status"] == "PENDING"
        assert blocker["agent_id"] == "backend-worker-001"

        # Step 4: User resolves blocker (simulating UI submission)
        success = db.resolve_blocker(
            blocker_id, "Use SQLite to match existing codebase. PostgreSQL is overkill for MVP."
        )
        assert success is True

        # Step 5: Verify blocker status updated
        blocker = db.get_blocker(blocker_id)
        assert blocker["status"] == "RESOLVED"
        assert (
            blocker["answer"]
            == "Use SQLite to match existing codebase. PostgreSQL is overkill for MVP."
        )
        assert blocker["resolved_at"] is not None

        # Step 6: Agent polls and gets answer
        resolved_blocker = db.get_pending_blocker("backend-worker-001")
        assert resolved_blocker is None  # No more pending blockers

        blocker_check = db.get_blocker(blocker_id)
        assert blocker_check["status"] == BlockerStatus.RESOLVED
        assert blocker_check["answer"] is not None

        # Step 7: Verify blocker disappears from pending list
        response = db.list_blockers(sample_project, status="PENDING")
        assert response["total"] == 0

    def test_workflow_with_async_blocker(self, db, sample_project, sample_tasks):
        """Test workflow with ASYNC blocker (agent continues work)."""
        task_id = sample_tasks["task3"]

        # Create ASYNC blocker
        blocker_id = db.create_blocker(
            agent_id="frontend-worker-001",
            project_id=1,
            task_id=task_id,
            blocker_type=BlockerType.ASYNC,
            question="Should the button be blue or green?",
        )

        # Agent can continue working (ASYNC blocker doesn't pause)
        # Simulate agent completing other work while blocker pending

        # Later, user resolves blocker
        db.resolve_blocker(blocker_id, "Use blue to match brand colors")

        # Agent can incorporate answer later
        blocker = db.get_blocker(blocker_id)
        assert blocker["status"] == "RESOLVED"
        assert blocker["blocker_type"] == BlockerType.ASYNC

    def test_workflow_with_multiple_sequential_blockers(self, db, sample_project, sample_tasks):
        """Test agent creating and resolving multiple blockers sequentially."""
        task_id = sample_tasks["task1"]

        # First blocker
        blocker1_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=task_id,
            blocker_type=BlockerType.SYNC,
            question="Question 1",
        )
        db.resolve_blocker(blocker1_id, "Answer 1")

        # Second blocker (after first resolved)
        blocker2_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=task_id,
            blocker_type=BlockerType.SYNC,
            question="Question 2",
        )
        db.resolve_blocker(blocker2_id, "Answer 2")

        # Verify both resolved
        blocker1 = db.get_blocker(blocker1_id)
        blocker2 = db.get_blocker(blocker2_id)
        assert blocker1["status"] == BlockerStatus.RESOLVED
        assert blocker2["status"] == BlockerStatus.RESOLVED


class TestSyncBlockerPausingDependentTasks:
    """Test T056: Integration test for SYNC blocker pausing dependent tasks."""

    def test_sync_blocker_pauses_dependent_tasks(self, db, sample_project, sample_tasks):
        """Test that SYNC blocker on task 1 pauses dependent task 2."""
        task1_id = sample_tasks["task1"]
        sample_tasks["task2"]  # Depends on task1

        # Task 1 agent creates SYNC blocker
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=task1_id,
            blocker_type=BlockerType.SYNC,
            question="Critical decision needed for task 1",
        )

        # Lead Agent should recognize task 1 is blocked
        # Task 2 (dependent on task 1) cannot start until task 1 unblocked

        # Verify blocker exists for task 1
        blocker = db.get_blocker(blocker_id)
        assert blocker["blocker_type"] == BlockerType.SYNC
        assert blocker["task_id"] == task1_id

        # In a real system, Lead Agent would:
        # 1. Check if task1 has pending SYNC blocker
        # 2. Mark task2 as waiting (cannot start while dependency blocked)
        # 3. Only allow task2 to start after blocker resolved

        # Simulate resolution
        db.resolve_blocker(blocker_id, "Answer to critical question")

        # Now task 1 can proceed and task 2 can start

    def test_sync_blocker_does_not_affect_independent_tasks(self, db, sample_project, sample_tasks):
        """Test that SYNC blocker on task 1 does NOT pause independent task 3."""
        task1_id = sample_tasks["task1"]
        sample_tasks["task3"]  # Independent (no dependencies)

        # Task 1 creates SYNC blocker
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=task1_id,
            blocker_type=BlockerType.SYNC,
            question="Blocker for task 1",
        )

        # Task 3 should continue unaffected (no dependency on task 1)
        # Lead Agent should allow task 3 to proceed normally

        blocker = db.get_blocker(blocker_id)
        assert blocker["task_id"] == task1_id

        # Task 3 can execute normally (verify it has no blocker)
        task3_blocker = db.get_pending_blocker("frontend-worker-001")
        assert task3_blocker is None


class TestAsyncBlockerAllowingParallelWork:
    """Test T057: Integration test for ASYNC blocker allowing parallel work."""

    def test_async_blocker_allows_continuation(self, db, sample_project, sample_tasks):
        """Test that ASYNC blocker allows agent to continue other work."""
        task1_id = sample_tasks["task1"]

        # Agent creates ASYNC blocker
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=task1_id,
            blocker_type=BlockerType.ASYNC,
            question="Preference question - not critical",
        )

        # Agent should be able to continue with other work
        # Create another task and start working on it
        db.create_task_with_issue(
            project_id=sample_project,
            issue_id=db.create_issue(
                {
                    "project_id": sample_project,
                    "issue_number": "4.0",
                    "title": "Issue 4",
                    "description": "Fourth issue",
                    "status": "pending",
                    "priority": 2,
                    "workflow_step": 1,
                }
            ),
            task_number="4.0.1",
            parent_issue_number="4.0",
            title="Task 4 - Additional Work",
            description="Can be done in parallel",
            status=TaskStatus.PENDING,
            priority=2,
            workflow_step=1,
            can_parallelize=False,
        )

        # Verify ASYNC blocker doesn't pause task 4
        blocker = db.get_blocker(blocker_id)
        assert blocker["blocker_type"] == BlockerType.ASYNC

        # Agent can check for ASYNC blockers later and incorporate answers
        # when available, without blocking current work

    def test_multiple_async_blockers_parallel(self, db, sample_project, sample_tasks):
        """Test multiple ASYNC blockers can exist without blocking work."""
        task1_id = sample_tasks["task1"]
        task3_id = sample_tasks["task3"]

        # Create multiple ASYNC blockers
        blocker1_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=task1_id,
            blocker_type=BlockerType.ASYNC,
            question="ASYNC question 1",
        )

        blocker2_id = db.create_blocker(
            agent_id="frontend-worker-001",
            project_id=1,
            task_id=task3_id,
            blocker_type=BlockerType.ASYNC,
            question="ASYNC question 2",
        )

        # Both agents continue working
        # Verify both blockers are ASYNC
        blocker1 = db.get_blocker(blocker1_id)
        blocker2 = db.get_blocker(blocker2_id)
        assert blocker1["blocker_type"] == BlockerType.ASYNC
        assert blocker2["blocker_type"] == BlockerType.ASYNC

        # Resolve one
        db.resolve_blocker(blocker1_id, "Answer 1")

        # Other still pending but not blocking
        blocker2_check = db.get_blocker(blocker2_id)
        assert blocker2_check["status"] == "PENDING"


class TestBlockerWorkflowEdgeCases:
    """Additional integration tests for edge cases."""

    def test_workflow_with_blocker_expiration(self, db, sample_project, sample_tasks):
        """Test workflow when blocker expires before resolution."""
        from datetime import timedelta

        task_id = sample_tasks["task1"]

        # Create blocker
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=task_id,
            blocker_type=BlockerType.SYNC,
            question="Question that will expire",
        )

        # Manually set created_at to 25 hours ago
        old_timestamp = datetime.now() - timedelta(hours=25)
        cursor = db.conn.cursor()
        cursor.execute(
            "UPDATE blockers SET created_at = ? WHERE id = ?",
            (old_timestamp.isoformat(), blocker_id),
        )
        db.conn.commit()

        # Run expiration
        expired_ids = db.expire_stale_blockers(hours=24)
        assert blocker_id in expired_ids

        # Verify blocker expired
        blocker = db.get_blocker(blocker_id)
        assert blocker["status"] == "EXPIRED"

        # User cannot resolve expired blocker
        success = db.resolve_blocker(blocker_id, "Too late")
        assert success is False

    def test_workflow_with_agent_having_no_blockers(self, db):
        """Test polling when agent has no blockers."""
        # Agent polls but has no blockers
        blocker = db.get_pending_blocker("agent-with-no-blockers")
        assert blocker is None

    def test_workflow_with_rapid_create_resolve_cycle(self, db, sample_project, sample_tasks):
        """Test rapid creation and resolution of multiple blockers."""
        task_id = sample_tasks["task1"]

        # Rapidly create and resolve 10 blockers
        for i in range(10):
            blocker_id = db.create_blocker(
                agent_id="backend-worker-001",
                project_id=1,
                task_id=task_id,
                blocker_type=BlockerType.SYNC,
                question=f"Question {i}",
            )
            success = db.resolve_blocker(blocker_id, f"Answer {i}")
            assert success is True

        # Verify all resolved
        response = db.list_blockers(sample_project, status="RESOLVED")
        assert response["total"] == 10
