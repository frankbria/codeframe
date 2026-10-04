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
from typing import Any

from codeframe.core.models import CallType
from codeframe.core.workspace import Workspace

logger = logging.getLogger(__name__)


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

    def complete(self, *args: Any, **kwargs: Any) -> Any:
        response = self._inner.complete(*args, **kwargs)
        try:
            record_llm_usage(
                self._workspace,
                model=getattr(response, "model", "") or getattr(self._inner, "model", "") or "",
                input_tokens=getattr(response, "input_tokens", 0) or 0,
                output_tokens=getattr(response, "output_tokens", 0) or 0,
                call_type=self._call_type,
            )
        except Exception:
            # Bookkeeping must never cost the user the answer they paid for.
            logger.warning("Could not record LLM usage", exc_info=True)
        return response

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)
