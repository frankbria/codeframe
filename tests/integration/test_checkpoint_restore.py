"""Integration tests for checkpoint restore workflow (T078).

Tests the complete checkpoint creation → modification → restore workflow
to ensure all components work together correctly.
"""

import subprocess
from pathlib import Path

import pytest

from codeframe.lib.checkpoint_manager import CheckpointManager
from codeframe.persistence.database import Database


@pytest.fixture
def project_setup(tmp_path: Path):
    """Setup a complete project with database and git."""
    project_dir = tmp_path / "integration_test_project"
    project_dir.mkdir()

    # Initialize git
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
        ["git", "config", "user.name", "Integration Test"],
        cwd=project_dir,
        check=True,
        capture_output=True
    )

    # Create initial files
    (project_dir / "README.md").write_text("# Integration Test Project")
    (project_dir / "main.py").write_text("def main():\n    print('Hello')")

    subprocess.run(
        ["git", "add", "."],
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

    # Setup database
    db_path = tmp_path / "integration_state.db"
    db = Database(db_path)
    db.initialize()

    # Create project
    cursor = db.conn.cursor()
    cursor.execute(
        """
        INSERT INTO projects (name, description, workspace_path, status, phase)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("integration_test", "Integration test project",
         str(project_dir), "active", "active")
    )
    db.conn.commit()
    project_id = cursor.lastrowid

    # Add some tasks
    cursor.execute(
        """
        INSERT INTO tasks
        (project_id, task_number, title, description, status, workflow_step)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (project_id, "1.1", "Setup database", "Initial task", "pending", 1)
    )
    cursor.execute(
        """
        INSERT INTO tasks
        (project_id, task_number, title, description, status, workflow_step)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (project_id, "1.2", "Add models", "Second task", "pending", 1)
    )
    db.conn.commit()

    # Add context items
    cursor.execute(
        """
        INSERT INTO context_items
        (agent_id, project_id, item_type, content, importance_score, current_tier)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("backend-agent", project_id, "TASK", "Build API endpoints", 0.9, "hot")
    )
    cursor.execute(
        """
        INSERT INTO context_items
        (agent_id, project_id, item_type, content, importance_score, current_tier)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("frontend-agent", project_id, "CODE", "React component", 0.7, "warm")
    )
    db.conn.commit()

    return {
        "project_dir": project_dir,
        "db": db,
        "project_id": project_id
    }


class TestCheckpointRestoreWorkflow:
    """Test complete checkpoint workflow integration."""

    def test_full_checkpoint_restore_workflow(self, project_setup):
        """Test complete workflow: create → modify → restore.

        This test verifies that:
        1. Checkpoint captures complete project state
        2. Modifications change all aspects (git, DB, context)
        3. Restore brings everything back to checkpoint state
        """
        project_dir = project_setup["project_dir"]
        db = project_setup["db"]
        project_id = project_setup["project_id"]

        # Create checkpoint manager
        checkpoint_mgr = CheckpointManager(
            db=db,
            project_root=project_dir,
            project_id=project_id
        )

        # ===== PHASE 1: Create checkpoint =====
        checkpoint = checkpoint_mgr.create_checkpoint(
            name="Before Major Changes",
            description="Checkpoint before implementing new features"
        )

        # Verify checkpoint was created
        assert checkpoint.id is not None
        assert checkpoint.name == "Before Major Changes"
        assert Path(checkpoint.database_backup_path).exists()
        assert Path(checkpoint.context_snapshot_path).exists()

        # Get initial state for comparison
        cursor = db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tasks")
        initial_task_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM context_items")
        initial_context_count = cursor.fetchone()[0]

        initial_main_py = (project_dir / "main.py").read_text()

        # ===== PHASE 2: Make modifications =====

        # Modify git (add new file, modify existing)
        (project_dir / "main.py").write_text(
            "def main():\n    print('Modified version')\n    print('New feature')"
        )
        (project_dir / "new_feature.py").write_text("def new_feature():\n    pass")

        subprocess.run(
            ["git", "add", "."],
            cwd=project_dir,
            check=True,
            capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Add new feature"],
            cwd=project_dir,
            check=True,
            capture_output=True
        )

        # Modify database (update tasks, add new task)
        cursor.execute(
            "UPDATE tasks SET status = ? WHERE task_number = ?",
            ("completed", "1.1")
        )
        cursor.execute(
            """
            INSERT INTO tasks
            (project_id, task_number, title, description, status, workflow_step)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_id, "1.3", "New task", "Added after checkpoint",
             "in_progress", 2)
        )
        db.conn.commit()

        # Modify context items (delete one, add new one)
        cursor.execute(
            "DELETE FROM context_items WHERE agent_id = ?",
            ("frontend-agent",)
        )
        cursor.execute(
            """
            INSERT INTO context_items
            (agent_id, project_id, item_type, content, importance_score, current_tier)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("test-agent", project_id, "ERROR", "Bug found", 0.95, "hot")
        )
        db.conn.commit()

        # Verify modifications were applied
        cursor.execute("SELECT COUNT(*) FROM tasks")
        modified_task_count = cursor.fetchone()[0]
        assert modified_task_count == initial_task_count + 1

        cursor.execute("SELECT status FROM tasks WHERE task_number = ?", ("1.1",))
        assert cursor.fetchone()["status"] == "completed"

        modified_main_py = (project_dir / "main.py").read_text()
        assert modified_main_py != initial_main_py
        assert (project_dir / "new_feature.py").exists()

        # ===== PHASE 3: Restore checkpoint =====
        result = checkpoint_mgr.restore_checkpoint(
            checkpoint_id=checkpoint.id,
            confirm=True
        )

        # Verify restore succeeded
        assert result["success"] is True
        assert result["checkpoint_name"] == "Before Major Changes"

        # ===== PHASE 4: Verify restoration =====

        # Verify git was restored
        restored_main_py = (project_dir / "main.py").read_text()
        assert restored_main_py == initial_main_py
        assert not (project_dir / "new_feature.py").exists()

        # Verify database was restored (get fresh cursor after restore)
        cursor = db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tasks")
        restored_task_count = cursor.fetchone()[0]
        assert restored_task_count == initial_task_count

        cursor.execute("SELECT status FROM tasks WHERE task_number = ?", ("1.1",))
        assert cursor.fetchone()["status"] == "pending"

        cursor.execute("SELECT COUNT(*) FROM tasks WHERE task_number = ?", ("1.3",))
        assert cursor.fetchone()[0] == 0

        # Verify context was restored
        cursor.execute("SELECT COUNT(*) FROM context_items")
        restored_context_count = cursor.fetchone()[0]
        assert restored_context_count == initial_context_count

        cursor.execute(
            "SELECT COUNT(*) FROM context_items WHERE agent_id = ?",
            ("frontend-agent",)
        )
        assert cursor.fetchone()[0] == 1  # Was restored

        cursor.execute(
            "SELECT COUNT(*) FROM context_items WHERE agent_id = ?",
            ("test-agent",)
        )
        assert cursor.fetchone()[0] == 0  # Was removed

    def test_checkpoint_list_and_metadata(self, project_setup):
        """Test checkpoint listing and metadata inspection."""
        project_dir = project_setup["project_dir"]
        db = project_setup["db"]
        project_id = project_setup["project_id"]

        checkpoint_mgr = CheckpointManager(
            db=db,
            project_root=project_dir,
            project_id=project_id
        )

        # Create multiple checkpoints with different states
        cp1 = checkpoint_mgr.create_checkpoint(
            "Checkpoint 1",
            "First checkpoint"
        )

        # Make some changes between checkpoints
        cursor = db.conn.cursor()
        cursor.execute(
            "UPDATE tasks SET status = ? WHERE task_number = ?",
            ("completed", "1.1")
        )
        db.conn.commit()

        cp2 = checkpoint_mgr.create_checkpoint(
            "Checkpoint 2",
            "After completing task 1.1"
        )

        cursor.execute(
            "UPDATE tasks SET status = ? WHERE task_number = ?",
            ("completed", "1.2")
        )
        db.conn.commit()

        cp3 = checkpoint_mgr.create_checkpoint(
            "Checkpoint 3",
            "After completing task 1.2"
        )

        # List checkpoints
        checkpoints = checkpoint_mgr.list_checkpoints()

        # Verify all checkpoints are listed
        assert len(checkpoints) == 3

        # Verify order (most recent first)
        assert checkpoints[0].name == "Checkpoint 3"
        assert checkpoints[1].name == "Checkpoint 2"
        assert checkpoints[2].name == "Checkpoint 1"

        # Verify metadata is present
        for cp in checkpoints:
            assert cp.metadata is not None
            assert cp.metadata.project_id == project_id
            assert cp.metadata.tasks_completed >= 0
            assert cp.metadata.tasks_total >= 0

        # Verify metadata progression
        # (tasks_completed should increase across checkpoints)
        assert checkpoints[0].metadata.tasks_completed >= checkpoints[1].metadata.tasks_completed
        assert checkpoints[1].metadata.tasks_completed >= checkpoints[2].metadata.tasks_completed

    def test_restore_checkpoint_with_diff_preview(self, project_setup):
        """Test restore with diff preview (confirm=False)."""
        project_dir = project_setup["project_dir"]
        db = project_setup["db"]
        project_id = project_setup["project_id"]

        checkpoint_mgr = CheckpointManager(
            db=db,
            project_root=project_dir,
            project_id=project_id
        )

        # Create checkpoint
        checkpoint = checkpoint_mgr.create_checkpoint("Test CP", "Test")

        # Make changes
        (project_dir / "main.py").write_text("def main():\n    print('Changed')")
        subprocess.run(
            ["git", "add", "."],
            cwd=project_dir,
            check=True,
            capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Changes"],
            cwd=project_dir,
            check=True,
            capture_output=True
        )

        # Get diff without restoring
        result = checkpoint_mgr.restore_checkpoint(
            checkpoint_id=checkpoint.id,
            confirm=False
        )

        # Verify diff is returned and restore didn't happen
        assert "diff" in result
        assert result["diff"] is not None
        assert "success" not in result  # No restore happened

        # Verify files weren't changed
        current_content = (project_dir / "main.py").read_text()
        assert "Changed" in current_content  # Still modified
