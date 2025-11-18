"""Simplified tests for blocker expiration functionality (049-human-in-loop, Phase 8)."""

from datetime import datetime, timedelta

import pytest

from codeframe.persistence.database import Database


@pytest.fixture
def temp_db():
    """Create a temporary in-memory database for testing."""
    # Use in-memory database for speed (no migrations needed)
    db = Database(":memory:")
    db.initialize(run_migrations=False)

    # Create test project
    cursor = db.conn.execute(
        """INSERT INTO projects (name, description, workspace_path, status)
           VALUES (?, ?, ?, ?)
           RETURNING id""",
        ("test-project", "Test project", "/tmp/test-workspace", "active"),
    )
    project_id = cursor.fetchone()[0]

    # Create test task to satisfy foreign key constraints
    db.conn.execute(
        """INSERT INTO tasks (id, project_id, title, description, status, priority)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (1, project_id, "Test Task", "Test task for blocker tests", "pending", 0),
    )
    db.conn.commit()

    yield db

    # Cleanup
    db.close()


class TestExpireStaleBlockers:
    """Test suite for expire_stale_blockers() database method."""

    def test_expire_stale_blockers_no_blockers(self, temp_db):
        """Test expire_stale_blockers with no blockers."""
        expired_ids = temp_db.expire_stale_blockers(hours=24)

        assert expired_ids == []

    def test_expire_stale_blockers_pending_within_threshold(self, temp_db):
        """Test expire_stale_blockers doesn't expire recent blockers."""
        # Create blocker 2 hours ago (within 24h threshold)
        recent_time = (datetime.now() - timedelta(hours=2)).isoformat()

        temp_db.conn.execute(
            """INSERT INTO blockers (agent_id, project_id, task_id, blocker_type, question, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("backend-worker-1", 1, 1, "SYNC", "Test question?", "PENDING", recent_time),
        )
        temp_db.conn.commit()

        expired_ids = temp_db.expire_stale_blockers(hours=24)

        assert expired_ids == []

    def test_expire_stale_blockers_pending_beyond_threshold(self, temp_db):
        """Test expire_stale_blockers expires stale blockers."""
        # Create blocker 25 hours ago (beyond 24h threshold)
        stale_time = (datetime.now() - timedelta(hours=25)).isoformat()

        cursor = temp_db.conn.execute(
            """INSERT INTO blockers (agent_id, project_id, task_id, blocker_type, question, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            ("backend-worker-1", 1, 1, "SYNC", "Stale question?", "PENDING", stale_time),
        )
        blocker_id = cursor.fetchone()[0]
        temp_db.conn.commit()

        expired_ids = temp_db.expire_stale_blockers(hours=24)

        assert len(expired_ids) == 1
        assert expired_ids[0] == blocker_id

        # Verify status was updated to EXPIRED
        blocker = temp_db.get_blocker(blocker_id)
        assert blocker["status"] == "EXPIRED"

    def test_expire_stale_blockers_custom_threshold(self, temp_db):
        """Test expire_stale_blockers with custom hour threshold."""
        # Create blocker 3 hours ago
        stale_time = (datetime.now() - timedelta(hours=3)).isoformat()

        cursor = temp_db.conn.execute(
            """INSERT INTO blockers (agent_id, project_id, task_id, blocker_type, question, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            ("backend-worker-1", 1, 1, "SYNC", "Question?", "PENDING", stale_time),
        )
        blocker_id = cursor.fetchone()[0]
        temp_db.conn.commit()

        # Expire with 2-hour threshold (blocker is 3 hours old, should expire)
        expired_ids = temp_db.expire_stale_blockers(hours=2)

        assert len(expired_ids) == 1
        assert expired_ids[0] == blocker_id

    def test_expire_stale_blockers_ignores_resolved(self, temp_db):
        """Test expire_stale_blockers ignores already resolved blockers."""
        # Create old blocker but already resolved
        stale_time = (datetime.now() - timedelta(hours=25)).isoformat()

        temp_db.conn.execute(
            """INSERT INTO blockers (agent_id, project_id, task_id, blocker_type, question, status, created_at, answer)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("backend-worker-1", 1, 1, "SYNC", "Question?", "RESOLVED", stale_time, "Answer"),
        )
        temp_db.conn.commit()

        expired_ids = temp_db.expire_stale_blockers(hours=24)

        assert expired_ids == []

    def test_expire_stale_blockers_ignores_already_expired(self, temp_db):
        """Test expire_stale_blockers ignores already expired blockers."""
        # Create old blocker but already expired
        stale_time = (datetime.now() - timedelta(hours=25)).isoformat()

        temp_db.conn.execute(
            """INSERT INTO blockers (agent_id, project_id, task_id, blocker_type, question, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("backend-worker-1", 1, 1, "SYNC", "Question?", "EXPIRED", stale_time),
        )
        temp_db.conn.commit()

        expired_ids = temp_db.expire_stale_blockers(hours=24)

        assert expired_ids == []

    def test_expire_stale_blockers_multiple_blockers(self, temp_db):
        """Test expire_stale_blockers handles multiple blockers correctly."""
        stale_time = (datetime.now() - timedelta(hours=25)).isoformat()
        recent_time = (datetime.now() - timedelta(hours=2)).isoformat()

        # Insert 2 stale blockers (all using task_id=1 to avoid FK constraints)
        cursor1 = temp_db.conn.execute(
            """INSERT INTO blockers (agent_id, project_id, task_id, blocker_type, question, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            ("backend-worker-1", 1, 1, "SYNC", "Stale 1?", "PENDING", stale_time),
        )
        stale_id_1 = cursor1.fetchone()[0]

        cursor2 = temp_db.conn.execute(
            """INSERT INTO blockers (agent_id, project_id, task_id, blocker_type, question, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            ("backend-worker-2", 1, 1, "ASYNC", "Stale 2?", "PENDING", stale_time),
        )
        stale_id_2 = cursor2.fetchone()[0]

        # Insert 1 recent blocker
        temp_db.conn.execute(
            """INSERT INTO blockers (agent_id, project_id, task_id, blocker_type, question, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("backend-worker-3", 1, 1, "SYNC", "Recent?", "PENDING", recent_time),
        )
        temp_db.conn.commit()

        expired_ids = temp_db.expire_stale_blockers(hours=24)

        assert len(expired_ids) == 2
        assert stale_id_1 in expired_ids
        assert stale_id_2 in expired_ids
