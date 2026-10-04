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
from datetime import date, datetime, timedelta, timezone
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
    """Sum of today's (UTC) recorded spend across the given workspaces.

    Raises:
        SpendLimitExceeded: a workspace's ledger exists but cannot be read.
    """
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
            # Fail closed: counting an unreadable ledger as $0 would hand out
            # budget the principal may already have spent (#1303 review).
            logger.warning("Could not read spend from %s: %s", db_path, exc)
            raise SpendLimitExceeded(
                f"Today's spend in {db_path.parent.parent.name} could not be read, "
                "so no new work can start until it can."
            ) from exc
        finally:
            conn.close()
    return total


def _refuse_unpriced_today(repo_paths: Iterable[Path]) -> None:
    """Refuse when today's ledger holds a call with no price (#1345).

    Its spend is unknown, so it cannot be counted: under a limit that makes it
    unbounded, and a refusal kept only in one request's state let the next
    request start fresh. Read from the ledger, it lasts the day.

    Raises:
        SpendLimitExceeded: an unpriced call was recorded today, or a ledger
            that exists cannot be read (fail closed, as spend_today_usd).
    """
    from codeframe.core.workspace import CODEFRAME_DIR, STATE_DB_NAME

    today = datetime.now(timezone.utc).date()
    start = today.strftime("%Y-%m-%d %H:%M:%S")
    end = (today + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    for db_path in {(Path(p) / CODEFRAME_DIR / STATE_DB_NAME).resolve() for p in repo_paths}:
        if not db_path.is_file():
            continue
        conn = sqlite3.connect(str(db_path))
        try:
            (unpriced,) = conn.execute(
                "SELECT COUNT(*) FROM token_usage WHERE estimated_cost_usd IS NULL "
                "AND timestamp >= ? AND timestamp < ?",
                (start, end),
            ).fetchone()
        except sqlite3.Error as exc:
            raise SpendLimitExceeded(
                f"Today's spend in {db_path.parent.parent.name} could not be read, "
                "so no new work can start until it can."
            ) from exc
        finally:
            conn.close()
        if unpriced:
            raise SpendLimitExceeded(
                "A model with no price was used today, so today's spend cannot be "
                "counted against the daily spend limit. Price it with "
                "CODEFRAME_MODEL_PRICING; the limit resets at midnight UTC."
            )


# Budget handed to runs still in flight, per principal and UTC day. A run's
# spend reaches token_usage only as it happens, so without this every
# concurrent start would be handed the same remainder (#1303 review). A run's
# own spend counts twice (recorded and held) until it ends, which errs toward
# refusing. Only today's holds count, so the limit still resets at midnight.
# ponytail: per process — fine for the single-worker server; a multi-worker
# deploy needs this in shared storage (same caveat as stream tickets, #745).
# A run that crosses midnight is not re-reserved for the new day.
_held: dict[int, list[tuple[date, float, Optional[str]]]] = {}
_held_lock = threading.Lock()


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _held_today(user_id: Optional[int]) -> float:
    if user_id is None:
        return 0.0
    today = _today()
    return sum(amount for day, amount, _ in _held.get(user_id, []) if day == today)


def _free_today(
    user_id: Optional[int], spent: float, limit: float
) -> float:
    """What is left after recorded spend and in-flight holds; raises when none."""
    held = _held_today(user_id)
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
    limit = daily_limit_usd()
    if limit is None:
        return None
    repo_paths = list(repo_paths)
    _refuse_unpriced_today(repo_paths)
    spent = spend_today_usd(repo_paths)  # disk I/O stays outside the lock
    with _held_lock:
        return _free_today(user_id, spent, limit)


def reserve_today_usd(
    user_id: int,
    repo_paths: Iterable[Path],
    share: int = 1,
    group: Optional[str] = None,
) -> Optional[float]:
    """Hold a slice of what is left for one run; ``release`` it when it ends.

    ``share`` is how many runs of ``group`` (a parallel batch's slots) may run
    at once. The remainder is divided by the slots its siblings do not already
    hold, counted under the same lock, so concurrent siblings get equal slices
    rather than each taking ``1/share`` of what the previous one left.

    Raises:
        SpendLimitExceeded: nothing is left.
    """
    limit = daily_limit_usd()
    if limit is None:
        return None
    # Read outside the lock: recorded spend only grows through runs, and those
    # are covered by holds, which are what the lock protects.
    repo_paths = list(repo_paths)
    _refuse_unpriced_today(repo_paths)
    spent = spend_today_usd(repo_paths)
    with _held_lock:
        holds = _held.setdefault(user_id, [])
        today = _today()
        siblings = sum(
            1 for day, _, g in holds if group is not None and g == group and day == today
        )
        amount = _free_today(user_id, spent, limit) / max(share - siblings, 1)
        holds.append((_today(), amount, group))
        return amount


def release(
    user_id: Optional[int], amount: Optional[float], group: Optional[str] = None
) -> None:
    """Return a hold taken by ``reserve_today_usd``; its real spend is recorded by now."""
    if user_id is None or amount is None:
        return
    with _held_lock:
        holds = _held.get(user_id, [])
        for i, (_, held, held_group) in enumerate(holds):
            if held == amount and held_group == group:
                del holds[i]
                break
        if not holds:
            _held.pop(user_id, None)
