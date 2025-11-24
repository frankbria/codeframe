"""Unit tests for CheckpointManager (Sprint 10 Phase 4: US-3).

Tests checkpoint creation, listing, restoration, and validation.
All tests should fail initially (TDD approach).
"""

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from unittest.mock import Mock, patch, MagicMock

import pytest

from codeframe.core.models import Checkpoint, CheckpointMetadata
from codeframe.lib.checkpoint_manager import CheckpointManager
from codeframe.persistence.database import Database


@pytest.fixture
def temp_project_dir(tmp_path: Path) -> Path:
    """Create a temporary project directory with git initialized."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()

    # Initialize git repository
    subprocess.run(
        ["git", "init"],
        cwd=project_dir,
        check=True,
        capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=project_dir,
        check=True,
        capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=project_dir,
        check=True,
        capture_output=True
    )

    # Create initial commit
    (project_dir / "README.md").write_text("# Test Project")
    subprocess.run(
        ["git", "add", "README.md"],
        cwd=project_dir,
        check=True,
        capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=project_dir,
        check=True,
        capture_output=True
    )

    return project_dir


@pytest.fixture
def db(tmp_path: Path) -> Database:
    """Create a test database."""
    db_path = tmp_path / "test_state.db"
    database = Database(db_path)
    database.initialize()
    return database


@pytest.fixture
def checkpoint_manager(
    db: Database,
    temp_project_dir: Path
) -> CheckpointManager:
    """Create a CheckpointManager instance for testing."""
    # Create project in database
    cursor = db.conn.cursor()
    cursor.execute(
        """
        INSERT INTO projects (name, description, workspace_path, status, phase)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("test_project", "Test project", str(temp_project_dir), "active", "active")
    )
    db.conn.commit()
    project_id = cursor.lastrowid

    return CheckpointManager(
        db=db,
        project_root=temp_project_dir,
        project_id=project_id
    )


class TestCheckpointCreation:
    """Test checkpoint creation functionality (T072)."""

    def test_create_checkpoint_saves_git_commit(
        self,
        checkpoint_manager: CheckpointManager,
        temp_project_dir: Path
    ):
        """Test that checkpoint creates a git commit."""
        # Create a file change to commit
        (temp_project_dir / "new_file.txt").write_text("New content")
        subprocess.run(
            ["git", "add", "new_file.txt"],
            cwd=temp_project_dir,
            check=True,
            capture_output=True
        )

        # Create checkpoint
        checkpoint = checkpoint_manager.create_checkpoint(
            name="Test Checkpoint",
            description="Testing checkpoint creation"
        )

        # Verify checkpoint has git commit
        assert checkpoint.git_commit is not None
        assert len(checkpoint.git_commit) >= 7  # Short SHA

        # Verify commit exists in git
        result = subprocess.run(
            ["git", "rev-parse", checkpoint.git_commit],
            cwd=temp_project_dir,
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

    def test_create_checkpoint_backs_up_database(
        self,
        checkpoint_manager: CheckpointManager
    ):
        """Test that checkpoint backs up the database."""
        checkpoint = checkpoint_manager.create_checkpoint(
            name="DB Backup Test",
            description="Testing database backup"
        )

        # Verify database backup path is set
        assert checkpoint.database_backup_path is not None

        # Verify backup file exists
        backup_path = Path(checkpoint.database_backup_path)
        assert backup_path.exists()
        assert backup_path.suffix == ".sqlite"
        assert "checkpoint" in backup_path.name

    def test_create_checkpoint_saves_context_snapshot(
        self,
        checkpoint_manager: CheckpointManager,
        db: Database
    ):
        """Test that checkpoint saves context items to JSON."""
        # Add some context items to database
        cursor = db.conn.cursor()
        cursor.execute(
            """
            INSERT INTO context_items
            (agent_id, project_id, item_type, content, importance_score, current_tier)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("test-agent", checkpoint_manager.project_id, "TASK",
             "Test task", 0.85, "hot")
        )
        db.conn.commit()

        # Create checkpoint
        checkpoint = checkpoint_manager.create_checkpoint(
            name="Context Test",
            description="Testing context snapshot"
        )

        # Verify context snapshot path is set
        assert checkpoint.context_snapshot_path is not None

        # Verify snapshot file exists and contains data
        snapshot_path = Path(checkpoint.context_snapshot_path)
        assert snapshot_path.exists()
        assert snapshot_path.suffix == ".json"

        # Verify content
        with open(snapshot_path) as f:
            snapshot_data = json.load(f)

        assert "checkpoint_id" in snapshot_data
        assert "project_id" in snapshot_data
        assert "context_items" in snapshot_data
        assert len(snapshot_data["context_items"]) > 0

    def test_create_checkpoint_generates_metadata(
        self,
        checkpoint_manager: CheckpointManager
    ):
        """Test that checkpoint generates metadata."""
        checkpoint = checkpoint_manager.create_checkpoint(
            name="Metadata Test",
            description="Testing metadata generation"
        )

        # Verify metadata exists and has expected fields
        assert checkpoint.metadata is not None
        assert checkpoint.metadata.project_id == checkpoint_manager.project_id
        assert checkpoint.metadata.phase is not None
        assert checkpoint.metadata.tasks_completed >= 0
        assert checkpoint.metadata.tasks_total >= 0
        assert isinstance(checkpoint.metadata.agents_active, list)
        assert checkpoint.metadata.context_items_count >= 0
        assert checkpoint.metadata.total_cost_usd >= 0.0

    def test_create_checkpoint_saves_to_database(
        self,
        checkpoint_manager: CheckpointManager,
        db: Database
    ):
        """Test that checkpoint is saved to database."""
        checkpoint = checkpoint_manager.create_checkpoint(
            name="DB Save Test",
            description="Testing database persistence"
        )

        # Verify checkpoint has ID (was saved)
        assert checkpoint.id is not None

        # Verify we can retrieve it from database
        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT * FROM checkpoints WHERE id = ?",
            (checkpoint.id,)
        )
        row = cursor.fetchone()

        assert row is not None
        assert row["name"] == "DB Save Test"
        assert row["description"] == "Testing database persistence"

    def test_create_checkpoint_creates_directory(
        self,
        temp_project_dir: Path,
        db: Database
    ):
        """Test that checkpoint creates .codeframe/checkpoints directory."""
        checkpoints_dir = temp_project_dir / ".codeframe" / "checkpoints"

        # Ensure directory doesn't exist initially
        if checkpoints_dir.exists():
            shutil.rmtree(checkpoints_dir)

        # Create project in database
        cursor = db.conn.cursor()
        cursor.execute(
            """
            INSERT INTO projects (name, description, workspace_path, status, phase)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("test_project", "Test project", str(temp_project_dir), "active", "active")
        )
        db.conn.commit()
        project_id = cursor.lastrowid

        # Create checkpoint manager (should create directory)
        checkpoint_mgr = CheckpointManager(
            db=db,
            project_root=temp_project_dir,
            project_id=project_id
        )

        # Verify directory was created by __init__
        assert checkpoints_dir.exists()
        assert checkpoints_dir.is_dir()


class TestCheckpointListing:
    """Test checkpoint listing functionality (T073)."""

    def test_list_checkpoints_returns_all(
        self,
        checkpoint_manager: CheckpointManager
    ):
        """Test listing all checkpoints."""
        # Create multiple checkpoints
        checkpoint_manager.create_checkpoint("First", "First checkpoint")
        checkpoint_manager.create_checkpoint("Second", "Second checkpoint")
        checkpoint_manager.create_checkpoint("Third", "Third checkpoint")

        # List checkpoints
        checkpoints = checkpoint_manager.list_checkpoints()

        # Verify all checkpoints are returned
        assert len(checkpoints) == 3
        assert all(isinstance(cp, Checkpoint) for cp in checkpoints)

    def test_list_checkpoints_sorted_by_date(
        self,
        checkpoint_manager: CheckpointManager
    ):
        """Test that checkpoints are sorted by created_at DESC."""
        import time

        # Create checkpoints with delays to ensure different timestamps
        cp1 = checkpoint_manager.create_checkpoint("First", "First")
        time.sleep(0.1)  # Wait 100ms
        cp2 = checkpoint_manager.create_checkpoint("Second", "Second")
        time.sleep(0.1)  # Wait 100ms
        cp3 = checkpoint_manager.create_checkpoint("Third", "Third")

        # List checkpoints
        checkpoints = checkpoint_manager.list_checkpoints()

        # Verify order (most recent first)
        assert checkpoints[0].name == "Third"
        assert checkpoints[1].name == "Second"
        assert checkpoints[2].name == "First"

    def test_list_checkpoints_empty(
        self,
        checkpoint_manager: CheckpointManager
    ):
        """Test listing when no checkpoints exist."""
        checkpoints = checkpoint_manager.list_checkpoints()
        assert checkpoints == []


class TestCheckpointRestore:
    """Test checkpoint restoration functionality (T074)."""

    def test_restore_checkpoint_reverts_git(
        self,
        checkpoint_manager: CheckpointManager,
        temp_project_dir: Path
    ):
        """Test that restore reverts git to checkpoint commit."""
        # Create initial file
        (temp_project_dir / "file1.txt").write_text("Version 1")
        subprocess.run(
            ["git", "add", "file1.txt"],
            cwd=temp_project_dir,
            check=True,
            capture_output=True
        )

        # Create checkpoint
        checkpoint = checkpoint_manager.create_checkpoint(
            "Before Changes",
            "State before modifications"
        )

        # Make additional changes
        (temp_project_dir / "file1.txt").write_text("Version 2")
        (temp_project_dir / "file2.txt").write_text("New file")
        subprocess.run(
            ["git", "add", "."],
            cwd=temp_project_dir,
            check=True,
            capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Additional changes"],
            cwd=temp_project_dir,
            check=True,
            capture_output=True
        )

        # Restore checkpoint
        result = checkpoint_manager.restore_checkpoint(
            checkpoint_id=checkpoint.id,
            confirm=True
        )

        # Verify git was reverted
        assert result["success"] is True
        assert (temp_project_dir / "file1.txt").read_text() == "Version 1"
        assert not (temp_project_dir / "file2.txt").exists()

    def test_restore_checkpoint_reverts_database(
        self,
        checkpoint_manager: CheckpointManager,
        db: Database
    ):
        """Test that restore reverts database to backup."""
        # Add initial data
        cursor = db.conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks
            (project_id, task_number, title, status, workflow_step)
            VALUES (?, ?, ?, ?, ?)
            """,
            (checkpoint_manager.project_id, "1.1", "Initial Task", "pending", 1)
        )
        db.conn.commit()

        # Create checkpoint
        checkpoint = checkpoint_manager.create_checkpoint(
            "Before Task Changes",
            "State before task modifications"
        )

        # Modify database
        cursor.execute(
            "UPDATE tasks SET status = ? WHERE task_number = ?",
            ("completed", "1.1")
        )
        cursor.execute(
            """
            INSERT INTO tasks
            (project_id, task_number, title, status, workflow_step)
            VALUES (?, ?, ?, ?, ?)
            """,
            (checkpoint_manager.project_id, "1.2", "New Task", "pending", 1)
        )
        db.conn.commit()

        # Restore checkpoint
        result = checkpoint_manager.restore_checkpoint(
            checkpoint_id=checkpoint.id,
            confirm=True
        )

        # Verify database was reverted
        assert result["success"] is True

        # Get fresh cursor from restored database connection
        cursor = db.conn.cursor()
        cursor.execute("SELECT status FROM tasks WHERE task_number = ?", ("1.1",))
        row = cursor.fetchone()
        assert row["status"] == "pending"

        cursor.execute("SELECT COUNT(*) FROM tasks WHERE task_number = ?", ("1.2",))
        count = cursor.fetchone()[0]
        assert count == 0

    def test_restore_checkpoint_reverts_context(
        self,
        checkpoint_manager: CheckpointManager,
        db: Database
    ):
        """Test that restore reverts context items."""
        # Add initial context
        cursor = db.conn.cursor()
        cursor.execute(
            """
            INSERT INTO context_items
            (agent_id, project_id, item_type, content, importance_score, current_tier)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("agent1", checkpoint_manager.project_id, "TASK",
             "Original task", 0.9, "hot")
        )
        db.conn.commit()

        # Create checkpoint
        checkpoint = checkpoint_manager.create_checkpoint(
            "Before Context Changes",
            "State before context modifications"
        )

        # Modify context
        cursor.execute(
            "DELETE FROM context_items WHERE content = ?",
            ("Original task",)
        )
        cursor.execute(
            """
            INSERT INTO context_items
            (agent_id, project_id, item_type, content, importance_score, current_tier)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("agent2", checkpoint_manager.project_id, "CODE",
             "New code", 0.5, "warm")
        )
        db.conn.commit()

        # Restore checkpoint
        result = checkpoint_manager.restore_checkpoint(
            checkpoint_id=checkpoint.id,
            confirm=True
        )

        # Verify context was reverted
        assert result["success"] is True

        # Get fresh cursor from restored database connection
        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM context_items WHERE content = ?",
            ("Original task",)
        )
        assert cursor.fetchone()[0] == 1

        cursor.execute(
            "SELECT COUNT(*) FROM context_items WHERE content = ?",
            ("New code",)
        )
        assert cursor.fetchone()[0] == 0


class TestCheckpointDiff:
    """Test checkpoint diff display functionality (T075)."""

    def test_restore_shows_diff_when_not_confirmed(
        self,
        checkpoint_manager: CheckpointManager,
        temp_project_dir: Path
    ):
        """Test that restore shows diff when confirm=False."""
        # Create file and checkpoint
        (temp_project_dir / "file.txt").write_text("Original")
        subprocess.run(
            ["git", "add", "file.txt"],
            cwd=temp_project_dir,
            check=True,
            capture_output=True
        )
        checkpoint = checkpoint_manager.create_checkpoint("CP1", "Test")

        # Make changes
        (temp_project_dir / "file.txt").write_text("Modified")
        subprocess.run(
            ["git", "add", "file.txt"],
            cwd=temp_project_dir,
            check=True,
            capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Changes"],
            cwd=temp_project_dir,
            check=True,
            capture_output=True
        )

        # Call restore without confirm
        result = checkpoint_manager.restore_checkpoint(
            checkpoint_id=checkpoint.id,
            confirm=False
        )

        # Verify diff is returned
        assert "diff" in result
        assert result["diff"] is not None
        assert "file.txt" in result["diff"]

    def test_show_diff_returns_git_diff_output(
        self,
        checkpoint_manager: CheckpointManager,
        temp_project_dir: Path
    ):
        """Test that _show_diff returns git diff output."""
        # Create initial state
        (temp_project_dir / "test.py").write_text("def foo(): pass")
        subprocess.run(
            ["git", "add", "test.py"],
            cwd=temp_project_dir,
            check=True,
            capture_output=True
        )
        checkpoint = checkpoint_manager.create_checkpoint("Test", "Test")

        # Make changes
        (temp_project_dir / "test.py").write_text("def bar(): pass")
        subprocess.run(
            ["git", "add", "test.py"],
            cwd=temp_project_dir,
            check=True,
            capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Update"],
            cwd=temp_project_dir,
            check=True,
            capture_output=True
        )

        # Get diff
        diff = checkpoint_manager._show_diff(checkpoint.git_commit)

        # Verify diff content
        assert diff is not None
        assert "test.py" in diff
        assert "-def foo(): pass" in diff or "foo" in diff
        assert "+def bar(): pass" in diff or "bar" in diff


class TestCheckpointValidation:
    """Test checkpoint validation functionality (T076)."""

    def test_invalid_checkpoint_fails_gracefully(
        self,
        checkpoint_manager: CheckpointManager
    ):
        """Test that invalid checkpoint ID fails gracefully."""
        with pytest.raises(ValueError, match="Checkpoint.*not found"):
            checkpoint_manager.restore_checkpoint(
                checkpoint_id=99999,
                confirm=True
            )

    def test_missing_database_backup_fails(
        self,
        checkpoint_manager: CheckpointManager
    ):
        """Test that missing database backup file fails gracefully."""
        # Create checkpoint
        checkpoint = checkpoint_manager.create_checkpoint("Test", "Test")

        # Delete database backup
        Path(checkpoint.database_backup_path).unlink()

        # Attempt restore
        with pytest.raises(FileNotFoundError, match="Checkpoint files missing"):
            checkpoint_manager.restore_checkpoint(
                checkpoint_id=checkpoint.id,
                confirm=True
            )

    def test_missing_context_snapshot_fails(
        self,
        checkpoint_manager: CheckpointManager
    ):
        """Test that missing context snapshot fails gracefully."""
        # Create checkpoint
        checkpoint = checkpoint_manager.create_checkpoint("Test", "Test")

        # Delete context snapshot
        Path(checkpoint.context_snapshot_path).unlink()

        # Attempt restore
        with pytest.raises(FileNotFoundError, match="Checkpoint files missing"):
            checkpoint_manager.restore_checkpoint(
                checkpoint_id=checkpoint.id,
                confirm=True
            )

    def test_validate_checkpoint_checks_files(
        self,
        checkpoint_manager: CheckpointManager
    ):
        """Test that _validate_checkpoint checks file existence."""
        # Create valid checkpoint
        checkpoint = checkpoint_manager.create_checkpoint("Valid", "Valid checkpoint")

        # Validate it
        is_valid = checkpoint_manager._validate_checkpoint(checkpoint)
        assert is_valid is True

        # Delete a file and revalidate
        Path(checkpoint.database_backup_path).unlink()
        is_valid = checkpoint_manager._validate_checkpoint(checkpoint)
        assert is_valid is False


class TestCheckpointContextSnapshot:
    """Test context snapshot functionality (T077)."""

    def test_checkpoint_context_snapshot_format(
        self,
        checkpoint_manager: CheckpointManager,
        db: Database
    ):
        """Test that context snapshot has correct format."""
        # Add context items
        cursor = db.conn.cursor()
        for i in range(3):
            cursor.execute(
                """
                INSERT INTO context_items
                (agent_id, project_id, item_type, content, importance_score, current_tier)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (f"agent{i}", checkpoint_manager.project_id, "TASK",
                 f"Task {i}", 0.8, "hot")
            )
        db.conn.commit()

        # Create checkpoint
        checkpoint = checkpoint_manager.create_checkpoint("Test", "Test")

        # Load and verify snapshot
        with open(checkpoint.context_snapshot_path) as f:
            snapshot = json.load(f)

        # Verify structure
        assert snapshot["checkpoint_id"] == checkpoint.id
        assert snapshot["project_id"] == checkpoint_manager.project_id
        assert "export_date" in snapshot
        assert len(snapshot["context_items"]) == 3

        # Verify context item structure
        item = snapshot["context_items"][0]
        assert "id" in item
        assert "agent_id" in item
        assert "item_type" in item
        assert "content" in item
        assert "importance_score" in item
        assert "tier" in item
        assert "created_at" in item
