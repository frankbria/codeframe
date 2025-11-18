"""
Unit tests for blocker database operations.

Tests T050-T054 from Phase 9: Testing & Validation
"""

import pytest_asyncio
import time
import threading
from datetime import datetime, timedelta
from codeframe.persistence.database import Database
from codeframe.core.models import BlockerType, TaskStatus


@pytest_asyncio.fixture
async def db():
    """Create in-memory database for testing."""
    database = Database(":memory:")
    # Initialize schema (migrations should be applied)
    database.initialize()
    yield database
    database.close()


@pytest_asyncio.fixture
async def sample_project(db):
    """Create a sample project for testing."""
    project_id = db.create_project(
        name="Test Project", repo_path="/tmp/test", description="Test project for blocker tests"
    )
    return project_id


@pytest_asyncio.fixture
async def sample_task(db, sample_project):
    """Create a sample task for testing."""
    # First create an issue
    issue_id = db.create_issue(
        {
            "project_id": sample_project,
            "issue_number": "1.0",
            "title": "Test Issue",
            "description": "Test issue for blocker tests",
            "status": "pending",
            "priority": 2,
            "workflow_step": 1,
        }
    )

    # Then create a task
    task_id = db.create_task_with_issue(
        project_id=sample_project,
        issue_id=issue_id,
        task_number="1.0.1",
        parent_issue_number="1.0",
        title="Test Task",
        description="Test task for blocker tests",
        status=TaskStatus.PENDING,
        priority=2,
        workflow_step=1,
        can_parallelize=False,
    )
    return task_id


class TestCreateBlocker:
    """Test T050: Unit test for create_blocker() database method."""

    def test_create_blocker_sync(self, db, sample_task, sample_project):
        """Test creating a SYNC blocker."""
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=sample_project,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="Should I use SQLite or PostgreSQL?",
        )

        assert blocker_id > 0

        # Verify blocker was created correctly
        blocker = db.get_blocker(blocker_id)
        assert blocker is not None
        assert blocker["agent_id"] == "backend-worker-001"
        assert blocker["task_id"] == sample_task
        assert blocker["blocker_type"] == BlockerType.SYNC
        assert blocker["question"] == "Should I use SQLite or PostgreSQL?"
        assert blocker["status"] == "PENDING"
        assert blocker["answer"] is None
        assert blocker["resolved_at"] is None
        assert blocker["created_at"] is not None

    def test_create_blocker_async(self, db, sample_task, sample_project):
        """Test creating an ASYNC blocker."""
        blocker_id = db.create_blocker(
            agent_id="frontend-worker-002",
            project_id=sample_project,
            task_id=sample_task,
            blocker_type=BlockerType.ASYNC,
            question="Should I use Tailwind or CSS Modules?",
        )

        blocker = db.get_blocker(blocker_id)
        assert blocker["blocker_type"] == BlockerType.ASYNC
        assert blocker["status"] == "PENDING"

    def test_create_blocker_without_task(self, db, sample_project):
        """Test creating a blocker without an associated task."""
        blocker_id = db.create_blocker(
            agent_id="test-agent-003",
            project_id=sample_project,
            task_id=None,
            blocker_type=BlockerType.SYNC,
            question="General question without task",
        )

        blocker = db.get_blocker(blocker_id)
        assert blocker["task_id"] is None
        assert blocker["status"] == "PENDING"

    def test_create_blocker_with_long_question(self, db, sample_task, sample_project):
        """Test creating a blocker with maximum length question."""
        long_question = "A" * 2000  # Max 2000 chars
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=sample_project,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question=long_question,
        )

        blocker = db.get_blocker(blocker_id)
        assert len(blocker["question"]) == 2000


class TestResolveBlocker:
    """Test T051: Unit test for resolve_blocker() database method."""

    def test_resolve_blocker_success(self, db, sample_task, sample_project):
        """Test successfully resolving a blocker."""
        # Create blocker
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=sample_project,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="What API key should I use?",
        )

        # Resolve blocker
        success = db.resolve_blocker(blocker_id, "Use key: sk-test-123")
        assert success is True

        # Verify resolution
        blocker = db.get_blocker(blocker_id)
        assert blocker["status"] == "RESOLVED"
        assert blocker["answer"] == "Use key: sk-test-123"
        assert blocker["resolved_at"] is not None

    def test_resolve_blocker_not_found(self, db):
        """Test resolving a non-existent blocker."""
        success = db.resolve_blocker(99999, "Some answer")
        assert success is False

    def test_resolve_blocker_with_long_answer(self, db, sample_task, sample_project):
        """Test resolving with maximum length answer."""
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=sample_project,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="Question?",
        )

        long_answer = "B" * 5000  # Max 5000 chars
        success = db.resolve_blocker(blocker_id, long_answer)
        assert success is True

        blocker = db.get_blocker(blocker_id)
        assert len(blocker["answer"]) == 5000


class TestDuplicateResolution:
    """Test T052: Unit test for resolve_blocker() twice (duplicate resolution)."""

    def test_resolve_blocker_twice(self, db, sample_task, sample_project):
        """Test that resolving an already-resolved blocker fails."""
        # Create blocker
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=sample_project,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="Question?",
        )

        # First resolution
        success1 = db.resolve_blocker(blocker_id, "First answer")
        assert success1 is True

        # Second resolution (should fail)
        success2 = db.resolve_blocker(blocker_id, "Second answer")
        assert success2 is False

        # Verify first answer persists
        blocker = db.get_blocker(blocker_id)
        assert blocker["status"] == "RESOLVED"
        assert blocker["answer"] == "First answer"

    def test_concurrent_resolution_race_condition(self, db, sample_task, sample_project):
        """Test concurrent resolution attempts (race condition)."""
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=sample_project,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="Question?",
        )

        # Simulate concurrent resolutions using threading
        # threading imported at top
        results = []

        def resolve_a():
            results.append(db.resolve_blocker(blocker_id, "Answer A"))

        def resolve_b():
            results.append(db.resolve_blocker(blocker_id, "Answer B"))

        thread_a = threading.Thread(target=resolve_a)
        thread_b = threading.Thread(target=resolve_b)

        thread_a.start()
        thread_b.start()
        thread_a.join()
        thread_b.join()

        # Exactly one should succeed
        successes = sum(1 for r in results if r is True)
        assert successes == 1

        # Verify only one answer was stored
        blocker = db.get_blocker(blocker_id)
        assert blocker["status"] == "RESOLVED"
        assert blocker["answer"] in ["Answer A", "Answer B"]


class TestGetPendingBlocker:
    """Test T053: Unit test for get_pending_blocker() agent polling."""

    def test_get_pending_blocker_exists(self, db, sample_task, sample_project):
        """Test retrieving a pending blocker for an agent."""
        # Create blocker
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=sample_project,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="Question?",
        )

        # Agent polls for blocker
        blocker = db.get_pending_blocker("backend-worker-001")
        assert blocker is not None
        assert blocker["id"] == blocker_id
        assert blocker["status"] == "PENDING"

    def test_get_pending_blocker_none(self, db):
        """Test polling when no blocker exists."""
        blocker = db.get_pending_blocker("nonexistent-agent")
        assert blocker is None

    def test_get_pending_blocker_after_resolution(self, db, sample_task, sample_project):
        """Test that resolved blockers are not returned."""
        # Create and resolve blocker
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=sample_project,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="Question?",
        )
        db.resolve_blocker(blocker_id, "Answer")

        # Agent should not see resolved blocker
        blocker = db.get_pending_blocker("backend-worker-001")
        assert blocker is None

    def test_get_pending_blocker_oldest_first(self, db, sample_task, sample_project):
        """Test that oldest blocker is returned first."""
        # Create multiple blockers
        id1 = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=sample_project,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="First question",
        )
        time.sleep(0.1)  # Ensure different timestamps
        db.create_blocker(
            agent_id="backend-worker-001",
            project_id=sample_project,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="Second question",
        )

        # Should return oldest blocker first
        blocker = db.get_pending_blocker("backend-worker-001")
        assert blocker["id"] == id1


class TestExpireStaleBlockers:
    """Test T054: Unit test for expire_stale_blockers()."""

    def test_expire_stale_blockers_none_stale(self, db, sample_task, sample_project):
        """Test expiration when no blockers are stale."""
        # Create recent blocker
        db.create_blocker(
            agent_id="backend-worker-001",
            project_id=sample_project,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="Recent question",
        )

        # Run expiration
        expired_ids = db.expire_stale_blockers(hours=24)
        assert len(expired_ids) == 0

    def test_expire_stale_blockers_one_stale(self, db, sample_task, sample_project):
        """Test expiring a single stale blocker."""
        # Create blocker with old timestamp (manual SQL update)
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=sample_project,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="Old question",
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

        # Verify status changed
        blocker = db.get_blocker(blocker_id)
        assert blocker["status"] == "EXPIRED"

    def test_expire_stale_blockers_multiple(self, db, sample_task, sample_project):
        """Test expiring multiple stale blockers."""
        # Create 3 stale blockers
        blocker_ids = []
        for i in range(3):
            blocker_id = db.create_blocker(
                agent_id=f"agent-{i}",
                project_id=sample_project,
                task_id=sample_task,
                blocker_type=BlockerType.SYNC,
                question=f"Question {i}",
            )
            blocker_ids.append(blocker_id)

            # Set to 25 hours ago
            old_timestamp = datetime.now() - timedelta(hours=25)
            cursor = db.conn.cursor()
            cursor.execute(
                "UPDATE blockers SET created_at = ? WHERE id = ?",
                (old_timestamp.isoformat(), blocker_id),
            )
            db.conn.commit()

        # Run expiration
        expired_ids = db.expire_stale_blockers(hours=24)
        assert len(expired_ids) == 3
        assert all(bid in expired_ids for bid in blocker_ids)

    def test_expire_stale_blockers_skips_resolved(self, db, sample_task, sample_project):
        """Test that resolved blockers are not expired."""
        # Create and resolve a stale blocker
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=sample_project,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="Question",
        )
        db.resolve_blocker(blocker_id, "Answer")

        # Set to 25 hours ago
        old_timestamp = datetime.now() - timedelta(hours=25)
        cursor = db.conn.cursor()
        cursor.execute(
            "UPDATE blockers SET created_at = ? WHERE id = ?",
            (old_timestamp.isoformat(), blocker_id),
        )
        db.conn.commit()

        # Run expiration
        expired_ids = db.expire_stale_blockers(hours=24)
        assert blocker_id not in expired_ids

        # Verify still resolved
        blocker = db.get_blocker(blocker_id)
        assert blocker["status"] == "RESOLVED"


class TestBlockerListWithEnrichment:
    """Test list_blockers() with enrichment (supplemental)."""

    def test_list_blockers_empty(self, db, sample_project):
        """Test listing blockers when none exist."""
        response = db.list_blockers(sample_project)
        assert response["total"] == 0
        assert response["pending_count"] == 0
        assert response["sync_count"] == 0
        assert len(response["blockers"]) == 0

    def test_list_blockers_with_data(self, db, sample_project, sample_task):
        """Test listing blockers with data."""
        # Create mixed blockers
        db.create_blocker(
            agent_id="backend-worker-001",
            project_id=sample_project,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="SYNC question",
        )
        blocker2_id = db.create_blocker(
            agent_id="backend-worker-002",
            project_id=sample_project,
            task_id=sample_task,
            blocker_type=BlockerType.ASYNC,
            question="ASYNC question",
        )
        db.resolve_blocker(blocker2_id, "Answer")

        # List all blockers
        response = db.list_blockers(sample_project)
        assert response["total"] == 2
        assert response["pending_count"] == 1
        assert response["sync_count"] == 1

    def test_list_blockers_filter_by_status(self, db, sample_project, sample_task):
        """Test filtering blockers by status."""
        blocker1_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=sample_project,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="Question 1",
        )
        blocker2_id = db.create_blocker(
            agent_id="backend-worker-002",
            project_id=sample_project,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="Question 2",
        )
        db.resolve_blocker(blocker2_id, "Answer")

        # Filter by PENDING
        response = db.list_blockers(sample_project, status="PENDING")
        assert response["total"] == 1
        assert response["blockers"][0]["id"] == blocker1_id

        # Filter by RESOLVED
        response = db.list_blockers(sample_project, status="RESOLVED")
        assert response["total"] == 1
        assert response["blockers"][0]["id"] == blocker2_id
