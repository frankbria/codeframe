"""Context management and score recalculation (T032, T041, T051, T052).

Provides centralized context management operations:
- Recalculate importance scores for all agent context items
- Batch score updates for existing items
- Tier reassignment based on updated scores (Phase 5)
- Flash save coordination (Phase 6)
- Token threshold detection

Part of 007-context-management Phase 4-6 (US2-US4).
"""

from typing import Dict
from datetime import datetime, UTC
import json
from codeframe.persistence.database import Database
from codeframe.lib.importance_scorer import calculate_importance_score, assign_tier
from codeframe.lib.token_counter import TokenCounter


class ContextManager:
    """Manages context scoring, tier assignment, and flash saves for agents."""

    # Token limit for flash save (180k tokens)
    TOKEN_LIMIT = 180000
    # Flash save threshold (80% of limit = 144k tokens)
    FLASH_SAVE_THRESHOLD = int(TOKEN_LIMIT * 0.8)

    def __init__(self, db: Database):
        """Initialize context manager.

        Args:
            db: Database instance for context operations
        """
        self.db = db
        self.token_counter = TokenCounter(cache_enabled=True)

    def recalculate_scores_for_agent(self, project_id: int, agent_id: str) -> int:
        """Recalculate importance scores for all context items belonging to an agent.

        Loads all context items for the agent on a project, recalculates their importance scores
        based on current age/access patterns, and updates the database.

        Use cases:
        - Periodic batch recalculation (e.g., every 5 minutes)
        - After significant time passage
        - Manual trigger from API endpoint

        Args:
            project_id: Project ID the agent is working on
            agent_id: Agent ID to recalculate scores for

        Returns:
            int: Number of context items updated

        Example:
            >>> manager = ContextManager(db)
            >>> updated_count = manager.recalculate_scores_for_agent(123, "backend-worker-001")
            >>> print(f"Updated {updated_count} items")
            Updated 150 items
        """
        # Load all context items for this agent on this project (all tiers)
        context_items = self.db.list_context_items(
            project_id=project_id, agent_id=agent_id, tier=None, limit=10000
        )

        if not context_items:
            return 0

        updated_count = 0

        for item in context_items:
            # Recalculate importance score
            new_score = calculate_importance_score(
                item_type=item["item_type"],
                created_at=datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")),
                access_count=item["access_count"],
                last_accessed=datetime.fromisoformat(item["last_accessed"].replace("Z", "+00:00")),
            )

            # Update score in database (keep tier unchanged for now - Phase 5 will update)
            # Convert current_tier from db (lowercase) to API tier format (uppercase)
            current_tier = item.get("current_tier", "warm").upper()
            self.db.update_context_item_tier(
                item_id=item["id"], tier=current_tier, importance_score=new_score
            )

            updated_count += 1

        return updated_count

    def update_tiers_for_agent(self, project_id: int, agent_id: str) -> int:
        """Recalculate importance scores and reassign tiers for all context items (T041).

        This is a combined operation that:
        1. Recalculates importance scores based on current age/access patterns
        2. Reassigns tiers (HOT/WARM/COLD) based on new scores

        Use cases:
        - Periodic maintenance (e.g., hourly tier updates)
        - After significant time passage causing tier shifts
        - Manual trigger to move aged items to lower tiers

        Args:
            project_id: Project ID the agent is working on
            agent_id: Agent ID to update tiers for

        Returns:
            int: Number of context items updated

        Example:
            >>> manager = ContextManager(db)
            >>> updated_count = manager.update_tiers_for_agent(123, "backend-worker-001")
            >>> print(f"Updated {updated_count} items with new tiers")
            Updated 150 items with new tiers
        """
        # Load all context items for this agent on this project (all tiers)
        context_items = self.db.list_context_items(
            project_id=project_id, agent_id=agent_id, tier=None, limit=10000
        )

        if not context_items:
            return 0

        updated_count = 0

        for item in context_items:
            # Recalculate importance score
            new_score = calculate_importance_score(
                item_type=item["item_type"],
                created_at=datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")),
                access_count=item["access_count"],
                last_accessed=datetime.fromisoformat(item["last_accessed"].replace("Z", "+00:00")),
            )

            # Reassign tier based on new score
            new_tier = assign_tier(new_score)

            # Update both score and tier in database
            self.db.update_context_item_tier(
                item_id=item["id"], tier=new_tier, importance_score=new_score
            )

            updated_count += 1

        return updated_count

    def should_flash_save(self, project_id: int, agent_id: str, force: bool = False) -> bool:
        """Check if flash save should be triggered (T051).

        Determines if an agent's context has exceeded the token threshold
        and flash save should be triggered.

        Args:
            project_id: Project ID the agent is working on
            agent_id: Agent ID to check
            force: If True, always return True (for manual triggers)

        Returns:
            bool: True if flash save should be triggered, False otherwise

        Example:
            >>> manager = ContextManager(db)
            >>> should_save = manager.should_flash_save(123, "backend-worker-001")
            >>> if should_save:
            ...     manager.flash_save(123, "backend-worker-001")
        """
        if force:
            return True

        # Get current context items
        context_items = self.db.list_context_items(
            project_id=project_id, agent_id=agent_id, tier=None, limit=10000
        )

        if not context_items:
            return False

        # Count total tokens
        total_tokens = self.token_counter.count_context_tokens(context_items)

        # Check if exceeds threshold (80% of 180k = 144k tokens)
        return total_tokens >= self.FLASH_SAVE_THRESHOLD

    def flash_save(self, project_id: int, agent_id: str) -> Dict:
        """Execute flash save for an agent (T052).

        Creates a checkpoint with full context state and archives COLD tier items
        to reduce memory footprint. Retains HOT and WARM items.

        Workflow:
        1. Load all context items for agent
        2. Count tokens before archival
        3. Create checkpoint with full context state (JSON)
        4. Archive COLD tier items (delete from active context)
        5. Count tokens after archival
        6. Calculate reduction percentage
        7. Return FlashSaveResponse

        Args:
            project_id: Project ID the agent is working on
            agent_id: Agent ID to flash save

        Returns:
            dict: Flash save response with checkpoint_id, tokens_before, tokens_after, reduction_percentage

        Example:
            >>> manager = ContextManager(db)
            >>> result = manager.flash_save(123, "backend-worker-001")
            >>> print(f"Reduced from {result['tokens_before']} to {result['tokens_after']} tokens")
            Reduced from 150000 to 50000 tokens
        """
        # STEP 1: Load all context items
        context_items = self.db.list_context_items(
            project_id=project_id, agent_id=agent_id, tier=None, limit=10000
        )

        # STEP 2: Count tokens before archival
        tokens_before = self.token_counter.count_context_tokens(context_items)

        # STEP 3: Create checkpoint with full context state
        checkpoint_data = {
            "project_id": project_id,
            "agent_id": agent_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "reason": "flash_save_triggered",
            "context_items": [
                {
                    "id": item["id"],
                    "item_type": item["item_type"],
                    "content": item["content"],
                    "importance_score": item["importance_score"],
                    "tier": item.get("current_tier", "warm"),
                    "access_count": item["access_count"],
                    "created_at": item["created_at"],
                    "last_accessed": item["last_accessed"],
                }
                for item in context_items
            ],
        }

        # Count items by tier
        hot_items = [item for item in context_items if item.get("current_tier") == "hot"]
        warm_items = [item for item in context_items if item.get("current_tier") == "warm"]
        cold_items = [item for item in context_items if item.get("current_tier") == "cold"]

        items_count = len(context_items)
        items_archived = len(cold_items)
        hot_items_retained = len(hot_items)

        # Create checkpoint in database
        checkpoint_id = self.db.create_checkpoint(
            agent_id=agent_id,
            checkpoint_data=json.dumps(checkpoint_data),
            items_count=items_count,
            items_archived=items_archived,
            hot_items_retained=hot_items_retained,
            token_count=tokens_before,
        )

        # STEP 4: Archive COLD tier items (delete from active context)
        self.db.archive_cold_items(project_id, agent_id)

        # STEP 5: Count tokens after archival (only HOT and WARM remain)
        remaining_items = self.db.list_context_items(
            project_id=project_id, agent_id=agent_id, tier=None, limit=10000
        )
        tokens_after = self.token_counter.count_context_tokens(remaining_items)

        # STEP 6: Calculate reduction percentage
        if tokens_before > 0:
            reduction_percentage = ((tokens_before - tokens_after) / tokens_before) * 100
        else:
            reduction_percentage = 0.0

        # STEP 7: Return FlashSaveResponse
        return {
            "checkpoint_id": checkpoint_id,
            "tokens_before": tokens_before,
            "tokens_after": tokens_after,
            "reduction_percentage": round(reduction_percentage, 2),
            "items_archived": items_archived,
            "hot_items_retained": hot_items_retained,
            "warm_items_retained": len(warm_items),
        }
