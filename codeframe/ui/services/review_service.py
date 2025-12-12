"""Code review service.

This module provides business logic for managing code review operations
and caching review results.
"""

from typing import Dict, Optional
import logging
from datetime import datetime, timezone

from codeframe.persistence.database import Database

logger = logging.getLogger(__name__)


class ReviewService:
    """Service for managing code review operations."""

    def __init__(self, db: Database, review_cache: Dict[int, dict]):
        """Initialize review service.

        Args:
            db: Database connection
            review_cache: Dictionary mapping task_id to review report dict
        """
        self.db = db
        self.review_cache = review_cache

    def cache_review(self, task_id: int, review_data: dict) -> None:
        """Cache a review report for quick access.

        Args:
            task_id: Task ID
            review_data: Review report data to cache
        """
        self.review_cache[task_id] = {
            **review_data,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.debug(f"Cached review for task {task_id}")

    def get_cached_review(self, task_id: int) -> Optional[dict]:
        """Get a cached review report.

        Args:
            task_id: Task ID

        Returns:
            Cached review data if exists, None otherwise
        """
        return self.review_cache.get(task_id)

    def clear_cache(self, task_id: Optional[int] = None) -> None:
        """Clear review cache.

        Args:
            task_id: Task ID to clear, or None to clear all
        """
        if task_id is not None:
            if task_id in self.review_cache:
                del self.review_cache[task_id]
                logger.debug(f"Cleared cache for task {task_id}")
        else:
            self.review_cache.clear()
            logger.debug("Cleared all review cache")

    def get_cache_stats(self) -> dict:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        return {
            "total_cached_reviews": len(self.review_cache),
            "cached_task_ids": list(self.review_cache.keys()),
        }

    async def get_review_summary(self, task_id: int) -> Optional[dict]:
        """Get review summary for a task.

        First checks cache, then falls back to database.

        Args:
            task_id: Task ID

        Returns:
            Review summary if exists, None otherwise
        """
        # Check cache first
        cached = self.get_cached_review(task_id)
        if cached:
            return cached

        # Fall back to database
        # Note: Database methods for reviews should be added to Database class
        # For now, return None if not cached
        logger.debug(f"No cached review found for task {task_id}")
        return None
