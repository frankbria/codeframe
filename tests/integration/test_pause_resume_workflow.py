"""Integration tests for Project.pause() and Project.resume() workflow.

Tests the complete pause → resume workflow to ensure all components
work together correctly, including flash save, checkpoints, and state restoration.
"""

import subprocess
from pathlib import Path
from datetime import datetime

import pytest

from codeframe.core.project import Project
from codeframe.core.models import ProjectStatus
from codeframe.persistence.database import Database


@pytest.fixture
def project_setup(tmp_path: Path):
    """Setup a complete project with database, git, and active agents."""
    project_dir = tmp_path / "pause_test_project"
    project_dir.mkdir()

    # Create .codeframe directory structure
    codeframe_dir = project_dir / ".codeframe"
    codeframe_dir.mkdir()
    (codeframe_dir / "checkpoints").mkdir()
    (codeframe_dir / "memory").mkdir()
    (codeframe_dir / "logs").mkdir()

    # Initialize git
    subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=project_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Pause Test"],
        cwd=project_dir,
        check=True,
        capture_output=True,
    )

    # Create initial files
    (project_dir / "README.md").write_text("# Pause Test Project")
    (project_dir / "main.py").write_text("def main():\n    print('Initial version')")

    subprocess.run(["git", "add", "."], cwd=project_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"], cwd=project_dir, check=True, capture_output=True
    )

    # Setup database
    db_path = codeframe_dir / "state.db"
    db = Database(db_path)
    db.initialize()

    # Create project
    cursor = db.conn.cursor()
    cursor.execute(
        """
        INSERT INTO projects (name, description, workspace_path, status, phase)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("pause_test", "Pause test project", str(project_dir), "active", "active"),
    )
    db.conn.commit()
    project_id = cursor.lastrowid

    # Add agents
    cursor.execute(
        """
        INSERT INTO agents (id, type, status)
        VALUES (?, ?, ?)
        """,
        ("backend-001", "backend", "idle"),
    )
    cursor.execute(
        """
        INSERT INTO agents (id, type, status)
        VALUES (?, ?, ?)
        """,
        ("frontend-001", "frontend", "idle"),
    )
    db.conn.commit()

    # Assign agents to project
    cursor.execute(
        """
        INSERT INTO project_agents (project_id, agent_id, role, is_active)
        VALUES (?, ?, ?, ?)
        """,
        (project_id, "backend-001", "backend_developer", True),
    )
    cursor.execute(
        """
        INSERT INTO project_agents (project_id, agent_id, role, is_active)
        VALUES (?, ?, ?, ?)
        """,
        (project_id, "frontend-001", "frontend_developer", True),
    )
    db.conn.commit()

    # Add context items to each agent (50k tokens worth)
    for i in range(50):
        cursor.execute(
            """
            INSERT INTO context_items
            (agent_id, project_id, item_type, content, importance_score, current_tier)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "backend-001",
                project_id,
                "TASK",
                f"Backend task {i}: Build API endpoint" + " " * 1000,  # ~1k tokens each
                0.3 if i < 20 else 0.6,  # Some COLD, some WARM
                "cold" if i < 20 else "warm",
            ),
        )

    for i in range(50):
        cursor.execute(
            """
            INSERT INTO context_items
            (agent_id, project_id, item_type, content, importance_score, current_tier)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "frontend-001",
                project_id,
                "CODE",
                f"Frontend code {i}: React component" + " " * 1000,  # ~1k tokens each
                0.3 if i < 20 else 0.6,
                "cold" if i < 20 else "warm",
            ),
        )
    db.conn.commit()

    # Create config file
    config_path = codeframe_dir / "config.json"
    config_path.write_text(
        '{"project_name": "pause_test", "project_type": "python"}'
    )

    return {"project_dir": project_dir, "db": db, "project_id": project_id}


class TestPauseResumeWorkflow:
    """Test complete pause/resume workflow integration."""

    def test_full_pause_resume_workflow(self, project_setup):
        """Test complete workflow: pause → modify → resume.

        Verifies that:
        1. Pause creates checkpoint and archives COLD context
        2. Modifications change git, DB, and files
        3. Resume restores exact state from checkpoint
        4. paused_at timestamp is set during pause and cleared during resume
        """
        project_dir = project_setup["project_dir"]
        db = project_setup["db"]
        project_id = project_setup["project_id"]

        # Create Project instance
        project = Project(project_dir)
        project.db = db
        project._status = ProjectStatus.ACTIVE

        # ===== PHASE 1: Pause project =====

        # Get initial context count
        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM context_items WHERE project_id = ?",
            (project_id,),
        )
        initial_context_count = cursor.fetchone()[0]
        assert initial_context_count == 100  # 50 backend + 50 frontend

        # Pause project
        result = project.pause(reason="user_request")

        # Verify pause succeeded
        assert result["success"] is True
        assert result["checkpoint_id"] is not None
        assert result["tokens_before"] > 0
        assert result["tokens_after"] < result["tokens_before"]
        assert result["reduction_percentage"] > 0
        assert result["items_archived"] > 0
        assert "paused_at" in result

        # Verify checkpoint was created
        checkpoint_id = result["checkpoint_id"]
        cursor.execute(
            "SELECT * FROM checkpoints WHERE id = ?", (checkpoint_id,)
        )
        checkpoint_row = cursor.fetchone()
        assert checkpoint_row is not None
        assert checkpoint_row["trigger"] == "pause"

        # Verify paused_at was set
        cursor.execute(
            "SELECT paused_at FROM projects WHERE id = ?", (project_id,)
        )
        paused_at = cursor.fetchone()[0]
        assert paused_at is not None
        assert paused_at == result["paused_at"]

        # Verify COLD context was archived
        cursor.execute(
            "SELECT COUNT(*) FROM context_items WHERE project_id = ?",
            (project_id,),
        )
        context_after_pause = cursor.fetchone()[0]
        assert context_after_pause < initial_context_count

        # Verify project status is PAUSED
        assert project._status == ProjectStatus.PAUSED

        # ===== PHASE 2: Make modifications =====

        # Modify file
        (project_dir / "main.py").write_text(
            "def main():\n    print('Modified during pause')\n"
        )

        # Add new file
        (project_dir / "new_feature.py").write_text("def new_feature():\n    pass")

        # Commit changes
        subprocess.run(
            ["git", "add", "."], cwd=project_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Modifications during pause"],
            cwd=project_dir,
            check=True,
            capture_output=True,
        )

        # Modify database (add task)
        cursor.execute(
            """
            INSERT INTO tasks
            (project_id, task_number, title, description, status, workflow_step)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                "2.1",
                "New task during pause",
                "Task added while paused",
                "pending",
                2,
            ),
        )
        db.conn.commit()

        # ===== PHASE 3: Resume from checkpoint =====

        # Resume project
        project.resume(checkpoint_id=checkpoint_id)

        # Verify paused_at was cleared
        cursor.execute(
            "SELECT paused_at FROM projects WHERE id = ?", (project_id,)
        )
        paused_at_after_resume = cursor.fetchone()[0]
        assert paused_at_after_resume is None

        # Verify project status is ACTIVE
        assert project._status == ProjectStatus.ACTIVE

        # Verify git was restored
        main_py_content = (project_dir / "main.py").read_text()
        assert "Initial version" in main_py_content
        assert "Modified during pause" not in main_py_content

        # Verify new file was removed
        assert not (project_dir / "new_feature.py").exists()

        # Verify database was restored
        cursor.execute(
            "SELECT COUNT(*) FROM tasks WHERE task_number = '2.1'"
        )
        new_task_count = cursor.fetchone()[0]
        assert new_task_count == 0  # Task added during pause should be gone

        # Verify context was restored
        cursor.execute(
            "SELECT COUNT(*) FROM context_items WHERE project_id = ?",
            (project_id,),
        )
        context_after_resume = cursor.fetchone()[0]
        assert context_after_resume == initial_context_count

    def test_pause_without_active_agents(self, tmp_path):
        """Test pause when no active agents exist (no flash save)."""
        project_dir = tmp_path / "no_agents_project"
        project_dir.mkdir()

        # Setup minimal project
        codeframe_dir = project_dir / ".codeframe"
        codeframe_dir.mkdir()
        (codeframe_dir / "checkpoints").mkdir()

        # Initialize git
        subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=project_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=project_dir,
            check=True,
            capture_output=True,
        )

        (project_dir / "README.md").write_text("# No Agents Test")
        subprocess.run(["git", "add", "."], cwd=project_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial"], cwd=project_dir, check=True, capture_output=True
        )

        # Setup database
        db_path = codeframe_dir / "state.db"
        db = Database(db_path)
        db.initialize()

        cursor = db.conn.cursor()
        cursor.execute(
            """
            INSERT INTO projects (name, status)
            VALUES (?, ?)
            """,
            ("no_agents_test", "active"),
        )
        db.conn.commit()
        project_id = cursor.lastrowid

        # Create config
        config_path = codeframe_dir / "config.json"
        config_path.write_text(
            '{"project_name": "no_agents_test", "project_type": "python"}'
        )

        # Create Project instance
        project = Project(project_dir)
        project.db = db
        project._status = ProjectStatus.ACTIVE

        # Pause (should succeed with no flash save)
        result = project.pause()

        # Verify pause succeeded
        assert result["success"] is True
        assert result["tokens_before"] == 0
        assert result["tokens_after"] == 0
        assert result["items_archived"] == 0
        assert result["checkpoint_id"] is not None

    def test_pause_resume_preserves_timestamps(self, project_setup):
        """Test that pause/resume preserves paused_at timestamp correctly."""
        project_dir = project_setup["project_dir"]
        db = project_setup["db"]
        project_id = project_setup["project_id"]

        project = Project(project_dir)
        project.db = db
        project._status = ProjectStatus.ACTIVE

        # Pause
        result1 = project.pause()
        paused_at_1 = result1["paused_at"]

        # Verify timestamp format (ISO 8601 with Z)
        assert paused_at_1.endswith("Z")
        assert "T" in paused_at_1
        datetime.fromisoformat(paused_at_1.replace("Z", "+00:00"))  # Should not raise

        # Resume
        project.resume(checkpoint_id=result1["checkpoint_id"])

        # Verify paused_at cleared
        cursor = db.conn.cursor()
        cursor.execute("SELECT paused_at FROM projects WHERE id = ?", (project_id,))
        paused_at_after_resume = cursor.fetchone()[0]
        assert paused_at_after_resume is None

        # Pause again
        project._status = ProjectStatus.ACTIVE
        result2 = project.pause()
        paused_at_2 = result2["paused_at"]

        # Verify second pause has different timestamp
        assert paused_at_1 != paused_at_2
