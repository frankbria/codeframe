"""Operator-set per-user daily LLM spend ceiling (#1303).

``CODEFRAME_USER_DAILY_COST_LIMIT_USD`` caps what each server principal may
spend per UTC day. Spend is read from ``token_usage`` in the workspaces the
principal runs in, and what is left clamps the workspace ``max_cost_usd`` for
the run being started (see ``cost_tracker.resolve_cost_cap``).

The CLI / auth-off principal (``user_id is None``) is the operator and is never
capped here; the caller decides that by not calling in.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

DAILY_LIMIT_ENV = "CODEFRAME_USER_DAILY_COST_LIMIT_USD"
#: How a batch hands the clamp to its ``cf work start`` children.
RUN_CEILING_ENV = "CODEFRAME_RUN_COST_CEILING_USD"


class SpendLimitExceeded(Exception):
    """The principal has used up today's spend ceiling."""


def _positive_float(raw: Optional[str]) -> Optional[float]:
    try:
        value = float(raw) if raw else None
    except ValueError:
        logger.warning("Ignoring non-numeric spend limit: %r", raw)
        return None
    return value if value is not None and value > 0 else None


def daily_limit_usd() -> Optional[float]:
    """The configured ceiling, or None when unset, non-numeric or <= 0."""
    return _positive_float(os.getenv(DAILY_LIMIT_ENV))


def run_ceiling_from_env() -> Optional[float]:
    """The clamp a parent batch passed down, or None."""
    return _positive_float(os.getenv(RUN_CEILING_ENV))


def spend_today_usd(repo_paths: Iterable[Path]) -> float:
    """Sum of today's (UTC) recorded spend across the given workspaces."""
    from codeframe.core.workspace import CODEFRAME_DIR, STATE_DB_NAME
    from codeframe.platform_store.repositories.token_repository import (
        TokenRepository,
    )

    total = 0.0
    for db_path in {(Path(p) / CODEFRAME_DIR / STATE_DB_NAME).resolve() for p in repo_paths}:
        if not db_path.is_file():
            continue  # a registry row can outlive its workspace
        conn = sqlite3.connect(str(db_path))
        try:
            total += TokenRepository(sync_conn=conn).get_costs_summary(1)["total_spend_usd"]
        except sqlite3.Error as exc:
            # ponytail: an unreadable DB under-counts rather than blocking every
            # run; fail closed here if a tenant can corrupt its own state.db.
            logger.warning("Could not read spend from %s: %s", db_path, exc)
        finally:
            conn.close()
    return total


def remaining_today_usd(repo_paths: Iterable[Path]) -> Optional[float]:
    """What is left of today's ceiling: None when no ceiling is set.

    Raises:
        SpendLimitExceeded: nothing is left.
    """
    limit = daily_limit_usd()
    if limit is None:
        return None
    spent = spend_today_usd(repo_paths)
    if spent >= limit:
        raise SpendLimitExceeded(
            f"Daily spend limit reached: ${spent:.2f} of ${limit:.2f} used today (UTC). "
            "It resets at midnight UTC; the operator sets it with "
            f"{DAILY_LIMIT_ENV}."
        )
    return limit - spent
