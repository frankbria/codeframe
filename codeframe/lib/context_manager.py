"""Context management and score recalculation (T032, T041).

Provides centralized context management operations:
- Recalculate importance scores for all agent context items
- Batch score updates for existing items
- Tier reassignment based on updated scores (Phase 5)
- Future: Flash save coordination

Part of 007-context-management Phase 4 (US2 - Importance Scoring) and Phase 5 (US3 - Automatic Tier Assignment).
"""

from typing import Dict
from datetime import datetime
from codeframe.persistence.database import Database
from codeframe.lib.importance_scorer import calculate_importance_score, assign_tier


class ContextManager:
    """Manages context scoring and tier assignment for agents."""

    def __init__(self, db: Database):
        """Initialize context manager.

        Args:
            db: Database instance for context operations
        """
        self.db = db

    def recalculate_scores_for_agent(self, agent_id: str) -> int:
        """Recalculate importance scores for all context items belonging to an agent.

        Loads all context items for the agent, recalculates their importance scores
        based on current age/access patterns, and updates the database.

        Use cases:
        - Periodic batch recalculation (e.g., every 5 minutes)
        - After significant time passage
        - Manual trigger from API endpoint

        Args:
            agent_id: Agent ID to recalculate scores for

        Returns:
            int: Number of context items updated

        Example:
            >>> manager = ContextManager(db)
            >>> updated_count = manager.recalculate_scores_for_agent("backend-worker-001")
            >>> print(f"Updated {updated_count} items")
            Updated 150 items
        """
        # Load all context items for this agent (all tiers)
        context_items = self.db.list_context_items(agent_id=agent_id, tier=None, limit=10000)

        if not context_items:
            return 0

        updated_count = 0

        for item in context_items:
            # Recalculate importance score
            new_score = calculate_importance_score(
                item_type=item['item_type'],
                created_at=datetime.fromisoformat(item['created_at'].replace('Z', '+00:00')),
                access_count=item['access_count'],
                last_accessed=datetime.fromisoformat(item['last_accessed'].replace('Z', '+00:00'))
            )

            # Update score in database (keep tier unchanged for now - Phase 5 will update)
            self.db.update_context_item_tier(
                item_id=item['id'],
                tier=item['tier'],
                importance_score=new_score
            )

            updated_count += 1

        return updated_count

    def update_tiers_for_agent(self, agent_id: str) -> int:
        """Recalculate importance scores and reassign tiers for all context items (T041).

        This is a combined operation that:
        1. Recalculates importance scores based on current age/access patterns
        2. Reassigns tiers (HOT/WARM/COLD) based on new scores

        Use cases:
        - Periodic maintenance (e.g., hourly tier updates)
        - After significant time passage causing tier shifts
        - Manual trigger to move aged items to lower tiers

        Args:
            agent_id: Agent ID to update tiers for

        Returns:
            int: Number of context items updated

        Example:
            >>> manager = ContextManager(db)
            >>> updated_count = manager.update_tiers_for_agent("backend-worker-001")
            >>> print(f"Updated {updated_count} items with new tiers")
            Updated 150 items with new tiers
        """
        # Load all context items for this agent (all tiers)
        context_items = self.db.list_context_items(agent_id=agent_id, tier=None, limit=10000)

        if not context_items:
            return 0

        updated_count = 0

        for item in context_items:
            # Recalculate importance score
            new_score = calculate_importance_score(
                item_type=item['item_type'],
                created_at=datetime.fromisoformat(item['created_at'].replace('Z', '+00:00')),
                access_count=item['access_count'],
                last_accessed=datetime.fromisoformat(item['last_accessed'].replace('Z', '+00:00'))
            )

            # Reassign tier based on new score
            new_tier = assign_tier(new_score)

            # Update both score and tier in database
            self.db.update_context_item_tier(
                item_id=item['id'],
                tier=new_tier,
                importance_score=new_score
            )

            updated_count += 1

        return updated_count
