"""Worker Agent implementation for CodeFRAME."""

from typing import Optional, List, Dict, Any
from codeframe.core.models import Task, AgentMaturity, ContextItemType, ContextTier


class WorkerAgent:
    """
    Worker Agent - Specialized agent for specific tasks (Backend, Frontend, Test, Review).
    """

    def __init__(
        self,
        agent_id: str,
        agent_type: str,
        provider: str,
        project_id: int | None = None,
        maturity: AgentMaturity = AgentMaturity.D1,
        system_prompt: str | None = None,
        db: Optional[Any] = None,
    ):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.project_id = project_id
        self.provider = provider
        self.maturity = maturity
        self.system_prompt = system_prompt
        self.current_task: Task | None = None
        self.db = db

    def execute_task(self, task: Task) -> dict:
        """
        Execute assigned task.

        Args:
            task: Task to execute

        Returns:
            Task execution result
        """
        self.current_task = task
        # TODO: Implement task execution with LLM provider
        return {"status": "completed", "output": "Task executed successfully"}

    def assess_maturity(self) -> None:
        """Assess and update agent maturity level."""
        # TODO: Implement maturity assessment
        pass

    async def flash_save(self) -> Dict[str, Any]:
        """Save current state before context compactification (T056).

        Creates a checkpoint with full context state and archives COLD tier items
        to reduce memory footprint. This method is called automatically when context
        approaches the token limit or manually via API.

        Returns:
            dict: Flash save response with checkpoint_id, tokens_before, tokens_after, reduction_percentage

        Raises:
            ValueError: If db is not initialized

        Example:
            >>> agent = BackendWorkerAgent(agent_id="backend-001", project_id=123, db=db)
            >>> result = await agent.flash_save()
            >>> print(f"Reduced from {result['tokens_before']} to {result['tokens_after']} tokens")
            Reduced from 150000 to 50000 tokens
        """
        if not self.db:
            raise ValueError("Database not initialized. Pass db parameter to __init__")

        if self.project_id is None:
            raise ValueError("project_id is required to flash_save")

        from codeframe.lib.context_manager import ContextManager

        # Create context manager and execute flash save
        context_mgr = ContextManager(db=self.db)
        result = context_mgr.flash_save(self.project_id, self.agent_id)

        return result

    async def should_flash_save(self) -> bool:
        """Check if flash save should be triggered (T057).

        Determines if this agent's context has exceeded the token threshold
        (80% of 180k = 144k tokens) and flash save should be triggered.

        Returns:
            bool: True if flash save should be triggered, False otherwise

        Raises:
            ValueError: If db is not initialized

        Example:
            >>> agent = BackendWorkerAgent(agent_id="backend-001", project_id=123, db=db)
            >>> if await agent.should_flash_save():
            ...     await agent.flash_save()
        """
        if not self.db:
            raise ValueError("Database not initialized. Pass db parameter to __init__")

        if self.project_id is None:
            raise ValueError("project_id is required to should_flash_save")

        from codeframe.lib.context_manager import ContextManager

        # Create context manager and check threshold
        context_mgr = ContextManager(db=self.db)
        return context_mgr.should_flash_save(self.project_id, self.agent_id, force=False)

    async def save_context_item(self, item_type: ContextItemType, content: str) -> str:
        """Save a context item for this agent.

        Args:
            item_type: Type of context (TASK, CODE, ERROR, TEST_RESULT, PRD_SECTION)
            content: The context content to save

        Returns:
            str: The created context item ID (UUID)

        Raises:
            ValueError: If db is not initialized or content is empty
        """
        if not self.db:
            raise ValueError("Database not initialized. Pass db parameter to __init__")

        if self.project_id is None:
            raise ValueError("project_id is required to save_context_item")

        if not content or not content.strip():
            raise ValueError("Content cannot be empty")

        # Call database create_context_item - score is auto-calculated (Phase 4)
        item_id = self.db.create_context_item(
            project_id=self.project_id,
            agent_id=self.agent_id,
            item_type=item_type.value,
            content=content,
        )

        return item_id

    async def load_context(
        self, tier: Optional[ContextTier] = ContextTier.HOT
    ) -> List[Dict[str, Any]]:
        """Load context items for this agent, optionally filtered by tier.

        Args:
            tier: Tier to filter by (HOT/WARM/COLD), or None for all tiers

        Returns:
            list[dict]: Context items for this agent

        Raises:
            ValueError: If db is not initialized
        """
        if not self.db:
            raise ValueError("Database not initialized. Pass db parameter to __init__")

        if self.project_id is None:
            raise ValueError("project_id is required to load_context")

        # Call database list_context_items with:
        # - project_id=self.project_id
        # - agent_id=self.agent_id
        # - tier=tier.value if tier else None
        # - limit=100
        tier_value = tier.value if tier else None
        items = self.db.list_context_items(
            project_id=self.project_id, agent_id=self.agent_id, tier=tier_value, limit=100
        )

        # Update access tracking for each loaded item
        for item in items:
            self.db.update_context_item_access(item["id"])

        return items

    async def get_context_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific context item by ID.

        Args:
            item_id: The context item ID (UUID string)

        Returns:
            dict | None: The context item, or None if not found

        Raises:
            ValueError: If db is not initialized
        """
        if not self.db:
            raise ValueError("Database not initialized. Pass db parameter to __init__")

        # Call database get_context_item
        item = self.db.get_context_item(item_id)

        # Update access tracking if item exists
        if item:
            self.db.update_context_item_access(item_id)

        return item

    async def update_tiers(self) -> int:
        """Recalculate scores and reassign tiers for all context items (T043).

        This method triggers batch tier reassignment for all context items
        belonging to this agent. It:
        1. Recalculates importance scores based on current age/access patterns
        2. Reassigns tiers (HOT >= 0.8, WARM 0.4-0.8, COLD < 0.4)

        Use cases:
        - Periodic maintenance (called by scheduler/cron)
        - Manual trigger to move aged items to lower tiers
        - After major time passage (e.g., daily cleanup)

        Returns:
            int: Number of context items updated with new tiers

        Raises:
            ValueError: If db is not initialized

        Example:
            >>> agent = FrontendWorkerAgent(agent_id="frontend-001", db=db)
            >>> updated = await agent.update_tiers()
            >>> print(f"Updated {updated} items")
            Updated 25 items
        """
        if not self.db:
            raise ValueError("Database not initialized. Pass db parameter to __init__")

        if self.project_id is None:
            raise ValueError("project_id is required to update_tiers")

        from codeframe.lib.context_manager import ContextManager

        # Create context manager and trigger tier updates
        context_mgr = ContextManager(db=self.db)
        updated_count = context_mgr.update_tiers_for_agent(self.project_id, self.agent_id)

        return updated_count
