"""Project management for CodeFRAME."""

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from codeframe.core.config import Config, ProjectConfig
from codeframe.core.models import ProjectStatus
from codeframe.persistence.database import Database

if TYPE_CHECKING:
    from codeframe.agents.lead_agent import LeadAgent

logger = logging.getLogger(__name__)


class Project:
    """Represents a CodeFRAME project."""

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.config = Config(project_dir)
        self.db: Optional[Database] = None
        self._status: ProjectStatus = ProjectStatus.INIT
        self._lead_agent: Optional["LeadAgent"] = None

    def _get_validated_project_id(self) -> tuple[int, str]:
        """Validate prerequisites and return project_id and API key.

        This method encapsulates all validation logic for both start() and get_lead_agent().

        Returns:
            Tuple of (project_id, api_key)

        Raises:
            RuntimeError: If database not initialized or API key missing/invalid
            ValueError: If project not found or has invalid structure
        """
        # Validate database
        if not self.db:
            raise RuntimeError(
                "Database not initialized. Call Project.create() or initialize database first."
            )

        # Validate API key existence
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY environment variable is required.\n"
                "Get your API key at: https://console.anthropic.com/"
            )

        # Validate API key format (Anthropic keys start with sk-ant-)
        if not api_key.startswith("sk-ant-"):
            raise RuntimeError(
                "Invalid ANTHROPIC_API_KEY format. Expected key starting with 'sk-ant-'.\n"
                "Check your API key at: https://console.anthropic.com/"
            )

        # Get project from database
        project_config = self.config.load()
        project_record = self.db.get_project(project_config.project_name)
        if not project_record:
            raise ValueError(f"Project '{project_config.project_name}' not found in database")

        # Validate database response structure (Zero Trust)
        if not isinstance(project_record, dict):
            raise ValueError("Invalid project record format from database")

        project_id = project_record.get("id")
        if not project_id:
            raise ValueError(
                f"Project '{project_config.project_name}' has invalid record: missing 'id' field"
            )

        if not isinstance(project_id, int):
            raise ValueError(
                f"Project '{project_config.project_name}' has invalid id: expected int, got {type(project_id).__name__}"
            )

        return project_id, api_key

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
        """Start project execution.

        Initializes LeadAgent and begins either:
        - Discovery phase if no PRD exists
        - Task execution if PRD already exists

        Raises:
            RuntimeError: If database not initialized or API key missing
            ValueError: If project not found in database
        """
        from codeframe.agents.lead_agent import LeadAgent

        # Validate prerequisites and get project_id
        project_id, api_key = self._get_validated_project_id()
        project_config = self.config.load()
        previous_status = self._status

        try:
            # Initialize LeadAgent
            logger.info(f"Initializing LeadAgent for project {project_id}")
            self._lead_agent = LeadAgent(
                project_id=project_id,
                db=self.db,
                api_key=api_key
            )

            # Check for existing PRD
            has_prd = self._lead_agent.has_existing_prd()

            if has_prd:
                # Resume with existing PRD
                logger.info("Resuming project with existing PRD")
                print(f"▶️  Resuming project: {project_config.project_name}")
                print("   Found existing PRD - ready for task execution")
                print("   Note: Call start_multi_agent_execution() on the LeadAgent to begin")

                self._status = ProjectStatus.ACTIVE
                activity_message = "Resuming with existing PRD (ready for task execution)"

            else:
                # Start discovery phase
                logger.info("Starting discovery phase for new project")
                print(f"🚀 Starting project: {project_config.project_name}")
                print("   Beginning Socratic discovery...")

                first_question = self._lead_agent.start_discovery()
                print(f"\n{first_question}")

                self._status = ProjectStatus.PLANNING
                activity_message = "Starting discovery phase"

            # Update database status
            self.db.update_project(project_id, {"status": self._status.value})
            logger.debug(f"Updated project status to {self._status.value}")

            # Note: WebSocket broadcasts should be done by the UI layer when needed
            # The core Project class doesn't require WebSocket functionality
            logger.debug(f"Project started: {activity_message}")

        except Exception as e:
            # Rollback status on error
            logger.error(f"Failed to start project: {e}", exc_info=True)
            try:
                self._status = previous_status
                # Only attempt database rollback if project_id was successfully retrieved
                if 'project_id' in locals():
                    self.db.update_project(project_id, {"status": previous_status.value})
                    logger.info(f"Rolled back project {project_id} status to {previous_status.value}")
            except Exception as rollback_err:
                logger.error(f"Failed to rollback status: {rollback_err}")
            raise

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
        cursor.execute("SELECT id FROM projects WHERE name = ?", (self.config.load().project_name,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("Project not found in database")

        project_id = row["id"]

        # Initialize checkpoint manager
        checkpoint_mgr = CheckpointManager(
            db=self.db, project_root=self.project_dir, project_id=project_id
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
        result = checkpoint_mgr.restore_checkpoint(checkpoint_id=checkpoint.id, confirm=True)

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
        """Get Lead Agent instance for interaction.

        Note: Call start() first to properly initialize the LeadAgent.
        This method returns the cached instance created by start(), or
        creates a new instance as fallback (requires API key in environment).

        Returns:
            LeadAgent instance

        Raises:
            RuntimeError: If database not initialized or API key missing (fallback mode)
        """
        from codeframe.agents.lead_agent import LeadAgent

        # Return cached instance if available (set by start())
        if self._lead_agent is not None:
            return self._lead_agent

        # Fallback: create new instance using shared validation logic
        project_id, api_key = self._get_validated_project_id()

        logger.debug("Creating new LeadAgent instance (fallback mode)")
        self._lead_agent = LeadAgent(
            project_id=project_id,
            db=self.db,
            api_key=api_key
        )

        return self._lead_agent

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
