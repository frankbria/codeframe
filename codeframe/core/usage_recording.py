"""Record THINK-stage LLM spend where the daily spend limit reads it (#1345).

The limit (core/spend_limit.py) sums each workspace's ``token_usage``, and only
ReactAgent wrote there. PRD stress-test and refine, discovery, task generation
and interactive session chat all spent tokens the limit never saw.

``UsageRecordingProvider`` wraps a provider and records every completion;
session chat, which streams, records from its relay with ``record_llm_usage``.
Agent runs are deliberately not wrapped: ReactAgent records its own calls, and
wrapping its provider would count them twice.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator, Optional

from codeframe.core.models import CallType
from codeframe.core.workspace import Workspace

logger = logging.getLogger(__name__)


@dataclass
class _Budget:
    limit: float
    spent: float = 0.0
    unmetered: bool = False


# The budget a route reserved for this request's planning calls. A context
# variable, not a parameter, so it reaches the provider through core code
# (discovery, task generation, the stress-test walk) unchanged: run_in_threadpool
# and asyncio.to_thread both copy the context into the worker thread.
_budget: ContextVar[Optional[_Budget]] = ContextVar("planning_budget", default=None)


def begin_budget(amount_usd: Optional[float]) -> None:
    """Set this context's planning budget until the context ends.

    For a request handler: each request runs in its own context, so the
    budget lasts exactly that request. Elsewhere, prefer ``spend_budget``.
    """
    _budget.set(_Budget(amount_usd) if amount_usd is not None else None)


@contextmanager
def spend_budget(amount_usd: Optional[float]) -> Iterator[None]:
    """Bound the planning calls made inside this block to ``amount_usd``.

    ``None`` (no limit configured, or an exempt principal) means unbounded.
    An entry-only check let a many-call run, like a recursive stress test,
    spend on past the ceiling (#1345 review).
    """
    token = _budget.set(_Budget(amount_usd) if amount_usd is not None else None)
    try:
        yield
    finally:
        _budget.reset(token)


def check_budget() -> None:
    """Raise ``SpendLimitExceeded`` if this context's budget is used up.

    Called before every billable model call made under a reserved budget.
    """
    from codeframe.core.spend_limit import SpendLimitExceeded

    budget = _budget.get()
    if budget is None:
        return
    if budget.unmetered:
        raise SpendLimitExceeded(
            "This model has no price, so its spend cannot be counted against "
            "the daily spend limit. Price it with CODEFRAME_MODEL_PRICING."
        )
    if budget.spent >= budget.limit:
        raise SpendLimitExceeded(
            f"This run used its ${budget.limit:.2f} share of today's spend "
            "limit. It resets at midnight UTC."
        )


def charge_budget(cost_usd: Optional[float]) -> None:
    """Count one call's cost against this context's budget (``None``: unpriced)."""
    budget = _budget.get()
    if budget is None:
        return
    if cost_usd is None:
        budget.unmetered = True
    else:
        budget.spent += cost_usd


def record_llm_usage(
    workspace: Workspace,
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    call_type: CallType,
) -> None:
    """Write one LLM call's usage to the workspace's ``token_usage``.

    The cost is computed from MODEL_PRICING; an unpriced model is stored
    without one (#932), never as $0.
    """
    from codeframe.lib.metrics_tracker import MetricsTracker
    from codeframe.platform_store.repositories.token_repository import TokenRepository

    conn = sqlite3.connect(str(workspace.db_path))
    try:
        MetricsTracker(db=TokenRepository(sync_conn=conn)).record_token_usage_sync(
            task_id=None,
            agent_id=call_type.value,
            project_id=0,
            model_name=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            call_type=call_type,
        )
    finally:
        conn.close()


class UsageRecordingProvider:
    """A provider that records each ``complete`` call's usage, and is
    otherwise the provider it wraps."""

    def __init__(self, inner: Any, workspace: Workspace, call_type: CallType) -> None:
        self._inner = inner
        self._workspace = workspace
        self._call_type = call_type

    @property
    def inner(self) -> Any:
        """The provider this one wraps."""
        return self._inner

    def complete(self, *args: Any, **kwargs: Any) -> Any:
        from codeframe.lib.metrics_tracker import MetricsTracker

        check_budget()
        response = self._inner.complete(*args, **kwargs)
        model = getattr(response, "model", "") or getattr(self._inner, "model", "") or ""
        input_tokens = getattr(response, "input_tokens", 0) or 0
        output_tokens = getattr(response, "output_tokens", 0) or 0
        if _budget.get() is not None:
            charge_budget(MetricsTracker.calculate_cost(model, input_tokens, output_tokens))
        try:
            record_llm_usage(
                self._workspace,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                call_type=self._call_type,
            )
        except Exception:
            # Bookkeeping must never cost the user the answer they paid for.
            logger.warning("Could not record LLM usage", exc_info=True)
        return response

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)
