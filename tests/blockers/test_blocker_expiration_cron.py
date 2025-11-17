"""Tests for blocker expiration cron job functionality (049-human-in-loop, Phase 8)."""

import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codeframe.persistence.database import Database
from codeframe.tasks.expire_blockers import expire_stale_blockers_job
from codeframe.core.models import TaskStatus


class TestExpireStaleBlockersCronJob:
    """Test suite for expire_stale_blockers_job cron function."""

    @pytest.mark.asyncio
    async def test_cron_job_no_blockers(self):
        """Test cron job with no blockers."""
        # Create temporary database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            db = Database(db_path)
            db.initialize(run_migrations=False)
            db.close()

            # Run cron job
            expired_count = await expire_stale_blockers_job(db_path=db_path, hours=24)

            assert expired_count == 0

        finally:
            Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_cron_job_with_stale_blocker(self):
        """Test cron job expires stale blocker."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Setup database
            db = Database(db_path)
            db.initialize(run_migrations=False)

            # Create test project and task
            cursor = db.conn.execute(
                """INSERT INTO projects (name, description, workspace_path, status)
                   VALUES (?, ?, ?, ?) RETURNING id""",
                ("test-project", "Test", "/tmp/test", "active"),
            )
            project_id = cursor.fetchone()[0]

            cursor = db.conn.execute(
                """INSERT INTO tasks (project_id, title, description, status, priority)
                   VALUES (?, ?, ?, ?, ?) RETURNING id""",
                (project_id, "Test Task", "Test", "pending", 0),
            )
            task_id = cursor.fetchone()[0]

            # Create stale blocker
            stale_time = (datetime.now() - timedelta(hours=25)).isoformat()
            cursor = db.conn.execute(
                """INSERT INTO blockers (agent_id, project_id, task_id, blocker_type, question, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id""",
                ("backend-worker-1", project_id, task_id, "SYNC", "Stale?", "PENDING", stale_time),
            )
            blocker_id = cursor.fetchone()[0]
            db.conn.commit()
            db.close()

            # Run cron job
            expired_count = await expire_stale_blockers_job(db_path=db_path, hours=24)

            assert expired_count == 1

            # Verify blocker was expired
            db = Database(db_path)
            db.initialize(run_migrations=False)
            blocker = db.get_blocker(blocker_id)
            assert blocker["status"] == "EXPIRED"
            db.close()

        finally:
            Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_cron_job_fails_associated_task(self):
        """Test cron job fails task when blocker expires."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Setup database
            db = Database(db_path)
            db.initialize(run_migrations=False)

            # Create test project
            cursor = db.conn.execute(
                """INSERT INTO projects (name, description, workspace_path, status)
                   VALUES (?, ?, ?, ?) RETURNING id""",
                ("test-project", "Test", "/tmp/test", "active"),
            )
            project_id = cursor.fetchone()[0]

            # Create task in progress
            cursor = db.conn.execute(
                """INSERT INTO tasks (project_id, title, description, status, priority)
                   VALUES (?, ?, ?, ?, ?) RETURNING id""",
                (project_id, "Test Task", "Test", "in_progress", 0),
            )
            task_id = cursor.fetchone()[0]

            # Create stale blocker
            stale_time = (datetime.now() - timedelta(hours=25)).isoformat()
            cursor = db.conn.execute(
                """INSERT INTO blockers (agent_id, project_id, task_id, blocker_type, question, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id""",
                ("backend-worker-1", project_id, task_id, "SYNC", "Stale?", "PENDING", stale_time),
            )
            blocker_id = cursor.fetchone()[0]
            db.conn.commit()
            db.close()

            # Run cron job
            expired_count = await expire_stale_blockers_job(db_path=db_path, hours=24)

            assert expired_count == 1

            # Verify task was failed
            db = Database(db_path)
            db.initialize(run_migrations=False)
            task = db.get_task(task_id)
            assert task["status"] == TaskStatus.FAILED.value
            db.close()

        finally:
            Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_cron_job_with_websocket_broadcast(self):
        """Test cron job broadcasts blocker_expired event."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Setup database
            db = Database(db_path)
            db.initialize(run_migrations=False)

            cursor = db.conn.execute(
                """INSERT INTO projects (name, description, workspace_path, status)
                   VALUES (?, ?, ?, ?) RETURNING id""",
                ("test-project", "Test", "/tmp/test", "active"),
            )
            project_id = cursor.fetchone()[0]

            cursor = db.conn.execute(
                """INSERT INTO tasks (project_id, title, description, status, priority)
                   VALUES (?, ?, ?, ?, ?) RETURNING id""",
                (project_id, "Test Task", "Test", "pending", 0),
            )
            task_id = cursor.fetchone()[0]

            stale_time = (datetime.now() - timedelta(hours=25)).isoformat()
            cursor = db.conn.execute(
                """INSERT INTO blockers (agent_id, project_id, task_id, blocker_type, question, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id""",
                ("backend-worker-1", project_id, task_id, "SYNC", "Stale?", "PENDING", stale_time),
            )
            blocker_id = cursor.fetchone()[0]
            db.conn.commit()
            db.close()

            # Mock WebSocket broadcast
            mock_ws_manager = MagicMock()

            with patch(
                "codeframe.ui.websocket_broadcasts.broadcast_blocker_expired", new_callable=AsyncMock
            ) as mock_broadcast:
                # Run cron job with WebSocket
                expired_count = await expire_stale_blockers_job(
                    db_path=db_path, hours=24, ws_manager=mock_ws_manager
                )

                assert expired_count == 1

                # Verify broadcast was called
                mock_broadcast.assert_called_once()
                call_kwargs = mock_broadcast.call_args.kwargs
                assert call_kwargs["blocker_id"] == blocker_id
                assert call_kwargs["agent_id"] == "backend-worker-1"
                assert call_kwargs["task_id"] == task_id

        finally:
            Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_cron_job_handles_blocker_without_task(self):
        """Test cron job handles blockers without associated tasks."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            db = Database(db_path)
            db.initialize(run_migrations=False)

            # Create project first (required by FOREIGN KEY)
            project_id = db.create_project(name="Test Project", description="Test project for blocker tests")

            # Create stale blocker without task_id
            stale_time = (datetime.now() - timedelta(hours=25)).isoformat()
            db.conn.execute(
                """INSERT INTO blockers (agent_id, project_id, task_id, blocker_type, question, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("backend-worker-1", project_id, None, "ASYNC", "Stale?", "PENDING", stale_time),
            )
            db.conn.commit()
            db.close()

            # Should not fail when task_id is None
            expired_count = await expire_stale_blockers_job(db_path=db_path, hours=24)

            assert expired_count == 1

        finally:
            Path(db_path).unlink(missing_ok=True)
