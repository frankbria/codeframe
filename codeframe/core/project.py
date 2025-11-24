"""Project management for CodeFRAME."""

from pathlib import Path
from typing import Optional
from codeframe.core.config import Config, ProjectConfig
from codeframe.core.models import ProjectStatus
from codeframe.persistence.database import Database


class Project:
    """Represents a CodeFRAME project."""

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.config = Config(project_dir)
        self.db: Optional[Database] = None
        self._status: ProjectStatus = ProjectStatus.INIT

    @classmethod
    def create(cls, project_name: str, project_dir: Optional[Path] = None) -> "Project":
        """
        Create a new CodeFRAME project.

        Args:
            project_name: Name of the project
            project_dir: Directory for the project (default: ./<project_name>)

        Returns:
            Initialized Project instance
        """
        if project_dir is None:
            project_dir = Path.cwd() / project_name

        project_dir.mkdir(parents=True, exist_ok=True)
        codeframe_dir = project_dir / ".codeframe"
        codeframe_dir.mkdir(exist_ok=True)

        # Create subdirectories
        (codeframe_dir / "checkpoints").mkdir(exist_ok=True)
        (codeframe_dir / "memory").mkdir(exist_ok=True)
        (codeframe_dir / "logs").mkdir(exist_ok=True)

        # Initialize project
        project = cls(project_dir)

        # Create default config
        default_config = ProjectConfig(
            project_name=project_name, project_type="python"  # Auto-detect in future
        )
        project.config.save(default_config)

        # Initialize database
        project.db = Database(codeframe_dir / "state.db")
        project.db.initialize()

        # Create initial project record
        project.db.create_project(project_name, ProjectStatus.INIT)

        return project

    def start(self) -> None:
        """Start project execution."""
        # TODO: Implement Lead Agent initialization and execution
        self._status = ProjectStatus.ACTIVE
        print(f"🚀 Starting project: {self.config.load().project_name}")
        print("Lead Agent will begin Socratic discovery...")

    def pause(self) -> None:
        """Pause project execution."""
        # TODO: Implement flash save before pause
        self._status = ProjectStatus.PAUSED
        print("⏸️ Project paused")

    def resume(self, checkpoint_id: Optional[int] = None) -> None:
        """Resume project execution from checkpoint.

        Args:
            checkpoint_id: Optional checkpoint ID to restore from.
                          If None, restores from most recent checkpoint.

        Raises:
            ValueError: If no checkpoints exist or checkpoint_id not found
            RuntimeError: If checkpoint restoration fails
        """
        from codeframe.lib.checkpoint_manager import CheckpointManager

        if not self.db:
            raise RuntimeError("Database not initialized. Call Project.create() first.")

        # Get project ID from database
        cursor = self.db.conn.cursor()
        cursor.execute(
            "SELECT id FROM projects WHERE name = ?",
            (self.config.load().project_name,)
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("Project not found in database")

        project_id = row["id"]

        # Initialize checkpoint manager
        checkpoint_mgr = CheckpointManager(
            db=self.db,
            project_root=self.project_dir,
            project_id=project_id
        )

        # Get checkpoint to restore
        if checkpoint_id:
            checkpoint = self.db.get_checkpoint_by_id(checkpoint_id)
            if not checkpoint:
                raise ValueError(f"Checkpoint {checkpoint_id} not found")
        else:
            # Get most recent checkpoint
            checkpoints = checkpoint_mgr.list_checkpoints()
            if not checkpoints:
                raise ValueError("No checkpoints available to restore from")
            checkpoint = checkpoints[0]  # Most recent

        print(f"▶️ Resuming project from checkpoint: {checkpoint.name}")
        print(f"   Created: {checkpoint.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   Commit: {checkpoint.git_commit[:7]}")

        # Restore checkpoint
        result = checkpoint_mgr.restore_checkpoint(
            checkpoint_id=checkpoint.id,
            confirm=True
        )

        if result["success"]:
            self._status = ProjectStatus.ACTIVE
            print(f"✓ Project resumed successfully from '{checkpoint.name}'")
            print(f"   {result.get('items_restored', 0)} context items restored")
        else:
            raise RuntimeError("Checkpoint restoration failed")

    def get_status(self) -> dict:
        """Get current project status."""
        # TODO: Implement comprehensive status gathering
        return {
            "project_name": self.config.load().project_name,
            "status": self._status.value,
            "completion_percentage": 0,  # Placeholder
            "active_tasks": [],
            "blocked_tasks": [],
        }

    def get_lead_agent(self):
        """Get Lead Agent instance for interaction."""
        # TODO: Implement Lead Agent retrieval
        from codeframe.agents.lead_agent import LeadAgent

        return LeadAgent(self)

    def chat(self, message: str) -> str:
        """
        Chat with Lead Agent.

        Args:
            message: User message

        Returns:
            Lead Agent response
        """
        lead = self.get_lead_agent()
        return lead.chat(message)
