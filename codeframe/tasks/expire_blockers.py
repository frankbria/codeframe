"""Stale blocker expiration cron job (049-human-in-loop, Phase 8).

This script runs hourly to expire blockers that have been pending for more
than 24 hours without resolution. Expired blockers trigger task failures
and WebSocket notifications to update the dashboard.

Usage:
    python -m codeframe.tasks.expire_blockers [--db-path PATH] [--hours HOURS]

Deployment:
    Add to crontab for hourly execution:
    0 * * * * cd /path/to/codeframe && python -m codeframe.tasks.expire_blockers

Environment:
    DATABASE_PATH: Override default database path (default: .codeframe/state.db)
"""

import asyncio
import logging
import sys

from codeframe.persistence.database import Database
from codeframe.core.models import TaskStatus

logger = logging.getLogger(__name__)


async def expire_stale_blockers_job(
    db_path: str = ".codeframe/state.db", hours: int = 24, ws_manager=None
) -> int:
    """Expire stale blockers and update affected tasks.

    Args:
        db_path: Path to SQLite database
        hours: Number of hours before blocker is considered stale (default: 24)
        ws_manager: Optional WebSocket manager for broadcasting events

    Returns:
        Number of blockers expired
    """
    db = Database(db_path)
    db.initialize(run_migrations=False)  # Connect to existing database

    try:
        # Expire stale blockers
        expired_ids = db.expire_stale_blockers(hours=hours)

        if not expired_ids:
            logger.info("No stale blockers found")
            return 0

        logger.info(f"Expired {len(expired_ids)} stale blocker(s): {expired_ids}")

        # Process each expired blocker
        for blocker_id in expired_ids:
            # Get blocker details
            blocker = db.get_blocker(blocker_id)
            if not blocker:
                logger.warning(f"Blocker {blocker_id} not found after expiration")
                continue

            task_id = blocker.get("task_id")
            agent_id = blocker.get("agent_id")
            blocker.get("question", "")[:100]  # Truncate for logging

            # Fail associated task (T049)
            if task_id:
                try:
                    task = db.get_task(task_id)
                    if task and task.get("status") != TaskStatus.FAILED.value:
                        db.update_task(
                            task_id=task_id,
                            updates={
                                "status": TaskStatus.FAILED.value,
                            },
                        )
                        logger.info(
                            f"Failed task {task_id} due to expired blocker {blocker_id}: {blocker.get('question', 'N/A')}"
                        )
                except Exception as e:
                    logger.error(f"Failed to update task {task_id} status: {e}")

            # Broadcast blocker_expired event (T047)
            if ws_manager:
                try:
                    from codeframe.ui.websocket_broadcasts import broadcast_blocker_expired

                    await broadcast_blocker_expired(
                        manager=ws_manager,
                        project_id=blocker.get("project_id", 1),  # Default to project 1
                        blocker_id=blocker_id,
                        agent_id=agent_id or "unknown",
                        task_id=task_id,
                        question=blocker.get("question", ""),
                    )
                    logger.debug(f"Broadcast blocker_expired event for blocker {blocker_id}")
                except Exception as e:
                    logger.warning(f"Failed to broadcast blocker_expired event: {e}")

        return len(expired_ids)

    finally:
        db.close()


def main():
    """CLI entry point for cron job."""
    import argparse

    parser = argparse.ArgumentParser(description="Expire stale blockers (pending >24h)")
    parser.add_argument(
        "--db-path",
        default=".codeframe/state.db",
        help="Path to SQLite database (default: .codeframe/state.db)",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Hours before blocker is considered stale (default: 24)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Run expiration job
    try:
        expired_count = asyncio.run(
            expire_stale_blockers_job(
                db_path=args.db_path, hours=args.hours, ws_manager=None  # No WebSocket in cron mode
            )
        )

        logger.info(f"Blocker expiration job complete: {expired_count} expired")
        sys.exit(0)

    except Exception as e:
        logger.error(f"Blocker expiration job failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
