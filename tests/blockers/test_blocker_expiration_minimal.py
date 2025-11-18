"""Minimal tests for blocker expiration to isolate timeout issues."""

import sqlite3
from datetime import datetime, timedelta


def test_expire_stale_blockers_direct_sql():
    """Test expire_stale_blockers using direct SQL without Database class."""
    # Create in-memory database
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # Create minimal schema
    conn.execute(
        """
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            workspace_path TEXT NOT NULL,
            status TEXT
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY,
            project_id INTEGER REFERENCES projects(id),
            title TEXT NOT NULL,
            description TEXT,
            status TEXT,
            priority INTEGER CHECK(priority BETWEEN 0 AND 4)
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE blockers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            task_id INTEGER,
            blocker_type TEXT NOT NULL CHECK(blocker_type IN ('SYNC', 'ASYNC')),
            question TEXT NOT NULL,
            answer TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'RESOLVED', 'EXPIRED')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        )
    """
    )

    # Insert test data
    conn.execute(
        "INSERT INTO projects (name, description, workspace_path, status) VALUES (?, ?, ?, ?)",
        ("test-project", "Test", "/tmp/test", "active"),
    )
    conn.execute(
        "INSERT INTO tasks (id, project_id, title, description, status, priority) VALUES (?, ?, ?, ?, ?, ?)",
        (1, 1, "Test Task", "Test", "pending", 0),
    )

    # Create stale blocker (25 hours old)
    stale_time = (datetime.now() - timedelta(hours=25)).isoformat()
    conn.execute(
        """
        INSERT INTO blockers (agent_id, task_id, blocker_type, question, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        ("backend-worker-1", 1, "SYNC", "Stale question?", "PENDING", stale_time),
    )
    conn.commit()

    # Expire stale blockers (same SQL as Database.expire_stale_blockers)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE blockers
        SET status = 'EXPIRED'
        WHERE status = 'PENDING'
        AND datetime(created_at) < datetime('now', '-24 hours')
        RETURNING id
    """
    )
    # CRITICAL: Fetch results BEFORE commit (SQLite requirement for RETURNING clause)
    expired_ids = [row[0] for row in cursor.fetchall()]
    conn.commit()

    # Verify
    assert len(expired_ids) == 1
    assert expired_ids[0] == 1

    # Check status was updated
    cursor.execute("SELECT status FROM blockers WHERE id = ?", (1,))
    status = cursor.fetchone()[0]
    assert status == "EXPIRED"

    conn.close()


if __name__ == "__main__":
    test_expire_stale_blockers_direct_sql()
    print("✓ Minimal test passed")
