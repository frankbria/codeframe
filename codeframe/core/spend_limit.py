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
import threading
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


# Budget handed to runs still in flight, per principal. A run's spend reaches
# token_usage only as it happens, so without this every concurrent start would
# be handed the same remainder (#1303 review). A run's own spend counts twice
# (recorded and held) until it ends, which errs toward refusing.
# ponytail: per process — fine for the single-worker server; a multi-worker
# deploy needs this in shared storage (same caveat as stream tickets, #745).
_held: dict[int, float] = {}
_held_lock = threading.Lock()


def _free_today(user_id: Optional[int], repo_paths: Iterable[Path]) -> Optional[float]:
    """What is left after recorded spend and in-flight holds; raises when none."""
    limit = daily_limit_usd()
    if limit is None:
        return None
    spent = spend_today_usd(repo_paths)
    held = _held.get(user_id, 0.0) if user_id is not None else 0.0
    if spent + held >= limit:
        in_flight = f" (${held:.2f} held by runs in progress)" if held else ""
        raise SpendLimitExceeded(
            f"Daily spend limit reached: ${spent:.2f} of ${limit:.2f} used today "
            f"(UTC){in_flight}. It resets at midnight UTC; the operator sets it "
            f"with {DAILY_LIMIT_ENV}."
        )
    return limit - spent - held


def remaining_today_usd(
    repo_paths: Iterable[Path], user_id: Optional[int] = None
) -> Optional[float]:
    """What is left of today's ceiling: None when no ceiling is set.

    Raises:
        SpendLimitExceeded: nothing is left.
    """
    with _held_lock:
        return _free_today(user_id, repo_paths)


def reserve_today_usd(
    user_id: int, repo_paths: Iterable[Path], share: int = 1
) -> Optional[float]:
    """Hold a slice of what is left for one run; ``release`` it when it ends.

    ``share`` splits the remainder between runs about to start together (a
    parallel batch's slots), so the first one cannot take all of it.

    Raises:
        SpendLimitExceeded: nothing is left.
    """
    with _held_lock:
        free = _free_today(user_id, repo_paths)
        if free is None:
            return None
        amount = free / max(share, 1)
        _held[user_id] = _held.get(user_id, 0.0) + amount
        return amount


def release(user_id: Optional[int], amount: Optional[float]) -> None:
    """Return a hold taken by ``reserve_today_usd``; its real spend is recorded by now."""
    if user_id is None or amount is None:
        return
    with _held_lock:
        left = _held.get(user_id, 0.0) - amount
        if left > 1e-9:
            _held[user_id] = left
        else:
            _held.pop(user_id, None)
