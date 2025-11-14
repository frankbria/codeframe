"""
Quickstart validation scenarios (049-human-in-loop, T069).

Validates the 5-minute tutorial and common patterns from quickstart.md work correctly.
"""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
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
        name="Quickstart Test Project",
        repo_path="/tmp/quickstart_test",
        description="Test project for quickstart validation"
    )
    return project_id


@pytest_asyncio.fixture
async def sample_task(db, sample_project):
    """Create a sample task for testing."""
    issue_id = db.create_issue({
        "project_id": sample_project,
        "issue_number": "1.0",
        "title": "Test Issue",
        "description": "Test issue",
        "status": "pending",
        "priority": 2,
        "workflow_step": 1
    })

    task_id = db.create_task_with_issue(
        project_id=sample_project,
        issue_id=issue_id,
        task_number="1.0.1",
        parent_issue_number="1.0",
        title="Implement data persistence layer",
        description="Test task for quickstart validation",
        status=TaskStatus.PENDING,
        priority=2,
        workflow_step=1,
        can_parallelize=False
    )
    return task_id


class TestFiveMinuteTutorial:
    """Test scenarios from the 5-minute tutorial."""

    def test_scenario_1_trigger_blocker(self, db, sample_task):
        """Scenario 1: Trigger a blocker from an agent."""
        # Agent creates blocker
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="Should the user table use UUID or auto-increment ID?"
        )

        assert blocker_id > 0
        print(f"✓ Blocker created: {blocker_id}")

    def test_scenario_2_view_blocker_in_dashboard(self, db, sample_project, sample_task):
        """Scenario 2: View blocker in dashboard."""
        # Create blocker
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="Should we use SQLite or PostgreSQL?"
        )

        # Simulate dashboard fetching blockers
        response = db.list_blockers(sample_project)

        assert response['total'] == 1
        assert response['pending_count'] == 1
        assert response['sync_count'] == 1

        blocker = response['blockers'][0]
        assert blocker['blocker_type'] == BlockerType.SYNC
        assert blocker['question'] == "Should we use SQLite or PostgreSQL?"
        assert blocker['agent_id'] == "backend-worker-001"
        print(f"✓ Blocker visible in dashboard: {blocker['question'][:50]}...")

    def test_scenario_3_resolve_blocker(self, db, sample_task):
        """Scenario 3: Resolve the blocker."""
        # Create blocker
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="Should we use SQLite or PostgreSQL?"
        )

        # User resolves blocker
        answer = "Use SQLite to match existing codebase. PostgreSQL is overkill for MVP."
        success = db.resolve_blocker(blocker_id, answer)

        assert success is True

        # Verify resolution
        blocker = db.get_blocker(blocker_id)
        assert blocker['status'] == 'RESOLVED'
        assert blocker['answer'] == answer
        assert blocker['resolved_at'] is not None
        print(f"✓ Blocker resolved with answer: {answer[:40]}...")

    def test_scenario_4_agent_resume(self, db, sample_task):
        """Scenario 4: Watch agent resume after resolution."""
        # Agent creates blocker
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="What API key should I use?"
        )

        # Agent polls (blocker still pending)
        pending = db.get_pending_blocker("backend-worker-001")
        assert pending is not None
        assert pending['id'] == blocker_id

        # User resolves
        db.resolve_blocker(blocker_id, "Use key: sk-test-123")

        # Agent polls again (blocker resolved, should get None)
        pending = db.get_pending_blocker("backend-worker-001")
        assert pending is None

        # Agent gets resolved blocker
        blocker = db.get_blocker(blocker_id)
        assert blocker['status'] == 'RESOLVED'
        assert blocker['answer'] == "Use key: sk-test-123"
        print(f"✓ Agent can resume with answer: {blocker['answer']}")


class TestCommonPatterns:
    """Test common patterns from quickstart."""

    def test_pattern_1_sync_blocker(self, db, sample_task):
        """Pattern 1: SYNC blocker (critical decision)."""
        # Agent encounters missing API key
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="ANTHROPIC_API_KEY environment variable not set. Please provide the API key."
        )

        # Wait for resolution (simulated)
        blocker = db.get_blocker(blocker_id)
        assert blocker['blocker_type'] == BlockerType.SYNC
        assert blocker['status'] == 'PENDING'

        # User provides API key
        db.resolve_blocker(blocker_id, "sk-ant-api03-test-key")

        # Agent gets answer
        blocker = db.get_blocker(blocker_id)
        assert blocker['answer'].startswith("sk-ant-api03-")
        print(f"✓ SYNC blocker pattern works: API key configured")

    def test_pattern_2_async_blocker(self, db, sample_task):
        """Pattern 2: ASYNC blocker (clarification)."""
        # Agent needs style preference but can continue
        blocker_id = db.create_blocker(
            agent_id="frontend-worker-001",
            project_id=1,
            task_id=sample_task,
            blocker_type=BlockerType.ASYNC,
            question="Should the button use primary blue (#0066CC) or teal (#00A8A8)?"
        )

        # Blocker is ASYNC, agent continues with default
        blocker = db.get_blocker(blocker_id)
        assert blocker['blocker_type'] == BlockerType.ASYNC

        # Later, user provides preference
        db.resolve_blocker(blocker_id, "Use teal #00A8A8 to match brand guidelines")

        # Agent checks later and applies answer
        blocker = db.get_blocker(blocker_id)
        assert blocker['status'] == 'RESOLVED'
        assert "#00A8A8" in blocker['answer']
        print(f"✓ ASYNC blocker pattern works: Preference applied")

    def test_pattern_3_multiple_blockers(self, db, sample_project):
        """Pattern 3: Multiple blockers workflow."""
        # Create issues and tasks for multiple agents
        issue_a = db.create_issue({
            "project_id": sample_project,
            "issue_number": "A.0",
            "title": "Backend Task",
            "description": "Backend work",
            "status": "pending",
            "priority": 2,
            "workflow_step": 1
        })
        task_a = db.create_task_with_issue(
            project_id=sample_project,
            issue_id=issue_a,
            task_number="A.0.1",
            parent_issue_number="A.0",
            title="Backend Task",
            description="Backend work",
            status=TaskStatus.PENDING,
            priority=2,
            workflow_step=1,
            can_parallelize=False
        )

        issue_b = db.create_issue({
            "project_id": sample_project,
            "issue_number": "B.0",
            "title": "Frontend Task",
            "description": "Frontend work",
            "status": "pending",
            "priority": 2,
            "workflow_step": 1
        })
        task_b = db.create_task_with_issue(
            project_id=sample_project,
            issue_id=issue_b,
            task_number="B.0.1",
            parent_issue_number="B.0",
            title="Frontend Task",
            description="Frontend work",
            status=TaskStatus.PENDING,
            priority=2,
            workflow_step=1,
            can_parallelize=False
        )

        # Multiple agents create blockers simultaneously
        blocker_a = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=task_a,
            blocker_type=BlockerType.SYNC,
            question="Use REST or GraphQL for API?"
        )

        blocker_b = db.create_blocker(
            agent_id="frontend-worker-001",
            project_id=1,
            task_id=task_b,
            blocker_type=BlockerType.ASYNC,
            question="Use Tailwind or CSS Modules?"
        )

        # Dashboard shows both blockers
        response = db.list_blockers(sample_project)
        assert response['total'] == 2
        assert response['sync_count'] == 1  # 1 SYNC, 1 ASYNC

        # Resolve SYNC first (blocking)
        db.resolve_blocker(blocker_a, "Use REST for consistency with existing endpoints")

        # Resolve ASYNC later
        db.resolve_blocker(blocker_b, "Use Tailwind, already integrated")

        # Verify both resolved
        blocker_a_resolved = db.get_blocker(blocker_a)
        blocker_b_resolved = db.get_blocker(blocker_b)
        assert blocker_a_resolved['status'] == 'RESOLVED'
        assert blocker_b_resolved['status'] == 'RESOLVED'
        print(f"✓ Multiple blockers pattern works: 2 blockers resolved")


class TestTroubleshooting:
    """Test troubleshooting scenarios from quickstart."""

    def test_blocker_not_appearing_wrong_project(self, db):
        """Troubleshooting: Wrong project_id filter."""
        project_1 = db.create_project(
            name="Project 1",
            description="Test project 1",
            source_type="empty"
        )
        project_2 = db.create_project(
            name="Project 2",
            description="Test project 2",
            source_type="empty"
        )

        issue = db.create_issue({
            "project_id": project_1,
            "issue_number": "1.0",
            "title": "Issue",
            "description": "Desc",
            "status": "pending",
            "priority": 2,
            "workflow_step": 1
        })
        task = db.create_task_with_issue(
            project_id=project_1,
            issue_id=issue,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Task",
            description="Desc",
            status=TaskStatus.PENDING,
            priority=2,
            workflow_step=1,
            can_parallelize=False
        )

        # Create blocker in project 1
        db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=task,
            blocker_type=BlockerType.SYNC,
            question="Test question"
        )

        # Query project 2 (wrong project)
        response = db.list_blockers(project_2)
        assert response['total'] == 0  # Blocker not visible

        # Query project 1 (correct project)
        response = db.list_blockers(project_1)
        assert response['total'] == 1  # Blocker visible
        print(f"✓ Troubleshooting: Project filter works correctly")

    def test_duplicate_resolutions(self, db, sample_task):
        """Troubleshooting: Duplicate resolutions (409 conflict)."""
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="Test question?"
        )

        # First user resolves
        success1 = db.resolve_blocker(blocker_id, "First answer")
        assert success1 is True

        # Second user tries to resolve (should fail)
        success2 = db.resolve_blocker(blocker_id, "Second answer")
        assert success2 is False

        # Verify first answer persists
        blocker = db.get_blocker(blocker_id)
        assert blocker['answer'] == "First answer"
        print(f"✓ Troubleshooting: Duplicate resolution prevented")

    def test_stale_blockers_expiration(self, db, sample_task):
        """Troubleshooting: Stale blockers (>24h) expire."""
        # Create blocker
        blocker_id = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="Old question"
        )

        # Manually set to 25 hours ago
        old_timestamp = datetime.now() - timedelta(hours=25)
        cursor = db.conn.cursor()
        cursor.execute(
            "UPDATE blockers SET created_at = ? WHERE id = ?",
            (old_timestamp.isoformat(), blocker_id)
        )
        db.conn.commit()

        # Run expiration
        expired_ids = db.expire_stale_blockers(hours=24)
        assert blocker_id in expired_ids

        # Verify status changed
        blocker = db.get_blocker(blocker_id)
        assert blocker['status'] == 'EXPIRED'
        print(f"✓ Troubleshooting: Stale blocker expired after 24h")


class TestAdvancedUsage:
    """Test advanced usage scenarios from quickstart."""

    def test_blocker_metrics(self, db, sample_project, sample_task):
        """Advanced: Query blocker metrics."""
        # Create mix of blockers
        blocker1 = db.create_blocker(
            agent_id="backend-worker-001",
            project_id=1,
            task_id=sample_task,
            blocker_type=BlockerType.SYNC,
            question="Question 1"
        )
        blocker2 = db.create_blocker(
            agent_id="backend-worker-002",
            project_id=1,
            task_id=sample_task,
            blocker_type=BlockerType.ASYNC,
            question="Question 2"
        )

        # Resolve one
        db.resolve_blocker(blocker1, "Answer 1")

        # Get metrics
        metrics = db.get_blocker_metrics(sample_project)

        assert metrics['total_blockers'] == 2
        assert metrics['resolved_count'] == 1
        assert metrics['pending_count'] == 1
        assert metrics['sync_count'] == 1
        assert metrics['async_count'] == 1
        assert metrics['avg_resolution_time_seconds'] is not None
        print(f"✓ Advanced: Blocker metrics available")

    def test_rate_limiting(self, db, sample_task):
        """Advanced: Rate limiting (10 blockers/minute per agent)."""
        # Create 10 blockers (at limit)
        for i in range(10):
            db.create_blocker(
                agent_id="backend-worker-001",
                project_id=1,
                task_id=sample_task,
                blocker_type=BlockerType.SYNC,
                question=f"Question {i}"
            )

        # 11th blocker should be rate limited
        with pytest.raises(ValueError, match="Rate limit exceeded"):
            db.create_blocker(
                agent_id="backend-worker-001",
                project_id=1,
                task_id=sample_task,
                blocker_type=BlockerType.SYNC,
                question="Question 11"
            )

        print(f"✓ Advanced: Rate limiting enforced (10/minute)")


if __name__ == "__main__":
    print("\n=== Quickstart Validation (T069) ===\n")
    print("Running validation scenarios from quickstart.md...\n")
    pytest.main([__file__, "-v", "--tb=short"])
