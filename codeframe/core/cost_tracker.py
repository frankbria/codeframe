"""Per-task spend accounting and the cost cap (#911, #1004).

`max_cost_usd` was honoured only by the built-in ReAct engine. The plan engine
(`--engine plan`) had no token accounting at all, so there was nothing to compare
a cap against: a user on that engine set a $5 cap and got no cost limiting, with
no way to tell an inert control from a working one — the exact complaint #911
was filed about, one engine over.

This module is that engine's missing half, extracted from `ReactAgent` rather
than reimplemented so the two cannot drift. It is headless: no FastAPI, no I/O
beyond reading the workspace config.

Delegated adapters (`--engine claude-code|codex|opencode|kilocode`) are
deliberately **not** covered. The external CLI does its own spending and reports
no usage back, so CodeFRAME cannot observe what a run cost. A cap that silently
binds nothing is the defect; `covers_engine()` states the boundary in code so
callers can surface it instead of pretending.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

#: Engines whose LLM calls go through our own provider, so tokens are visible.
#: Everything else spends inside a subprocess we cannot meter.
METERED_ENGINES = frozenset({"react", "plan", "builtin"})


def covers_engine(engine: str) -> bool:
    """Whether a cost cap can actually bind for ``engine``.

    False for the delegated adapters. Callers should say so rather than show a
    limit that cannot fire.
    """
    return (engine or "").strip().lower() in METERED_ENGINES


def resolve_cost_cap(repo_path: Path) -> Optional[float]:
    """The configured per-task spend cap, or None when unset.

    Read from the same ``.codeframe/config.yaml`` the Settings page writes.
    """
    from codeframe.core.config import load_environment_config

    try:
        env_config = load_environment_config(repo_path)
    except Exception as exc:  # pragma: no cover - config read is best effort
        logger.warning("Could not read the cost cap: %s", exc)
        return None

    cap = getattr(env_config, "max_cost_usd", None) if env_config else None
    if cap is None:
        return None
    try:
        cap = float(cap)
    except (TypeError, ValueError):
        logger.warning("Ignoring non-numeric max_cost_usd: %r", cap)
        return None
    # 0 would stop before the first call; treat it as "no cap" rather than
    # bricking every run, and let validation reject negatives upstream.
    return cap if cap > 0 else None


class CostCapExceeded(RuntimeError):
    """Raised when a spending loop must stop. Carries the user-facing reason."""


class CostTracker:
    """Accumulates token usage and answers "may I make another call?".

    ``prior_cost_usd`` is spend already recorded against this task by earlier
    runs. Without it, answering a blocker and resuming would hand the task a
    fresh full budget every time — a cap trivially bypassed by clicking resume
    (#911 review).
    """

    def __init__(
        self,
        cap_usd: Optional[float] = None,
        prior_cost_usd: float = 0.0,
    ) -> None:
        self.cap_usd = cap_usd
        self.prior_cost_usd = prior_cost_usd
        self.records: list[dict] = []

    # -- accumulation ---------------------------------------------------

    def record(
        self,
        *,
        model: str,
        input_tokens: int,
        output_tokens: int,
        call_type: str = "task_execution",
    ) -> None:
        self.records.append(
            {
                "model": model or "",
                "input_tokens": int(input_tokens or 0),
                "output_tokens": int(output_tokens or 0),
                "call_type": call_type,
            }
        )

    def record_response(self, response, call_type: str = "task_execution") -> None:
        """Record an ``LLMResponse`` directly — the common case."""
        self.record(
            model=getattr(response, "model", "") or "",
            input_tokens=getattr(response, "input_tokens", 0) or 0,
            output_tokens=getattr(response, "output_tokens", 0) or 0,
            call_type=call_type,
        )

    # -- measurement ----------------------------------------------------

    @property
    def total_tokens(self) -> tuple[int, int]:
        return (
            sum(r["input_tokens"] for r in self.records),
            sum(r["output_tokens"] for r in self.records),
        )

    def models_used(self) -> set[str]:
        return {r["model"] for r in self.records}

    def estimate_cost(self) -> float:
        """USD across the accumulated records. 0.0 on any error."""
        try:
            from codeframe.lib.metrics_tracker import MetricsTracker

            total = 0.0
            for record in self.records:
                cost = MetricsTracker.calculate_cost(
                    record["model"], record["input_tokens"], record["output_tokens"]
                )
                # None = unpriced; skip rather than adding 0.0. Whether anything
                # was unpriced is asked separately, by has_unpriced_records().
                if cost is not None:
                    total += cost
            return round(total, 6)
        except Exception:
            return 0.0

    def has_unpriced_records(self) -> bool:
        """True when any recorded call used a model with no pricing data.

        Asked directly rather than inferred from a $0 outcome (#932): a
        deployment can legitimately price a local model at 0/0 via
        CODEFRAME_MODEL_PRICING, and "spent nothing" would then read as "cannot
        measure" and abort a correctly-measured free run.
        """
        try:
            from codeframe.lib.metrics_tracker import MetricsTracker

            return any(
                MetricsTracker.calculate_cost(
                    r["model"], r["input_tokens"], r["output_tokens"]
                )
                is None
                for r in self.records
            )
        except Exception:
            return False

    # -- the gate -------------------------------------------------------

    def cap_message(
        self,
        spent: Optional[float] = None,
        unpriced: Optional[bool] = None,
    ) -> Optional[str]:
        """Why spending must stop, or None to continue.

        The single place any spending loop asks permission. A loop that skips it
        — a verification/self-correction retry, say — is not capped at all
        (#911 review).

        ``spent`` and ``unpriced`` are the measurements. They are parameters so
        a caller that already has them (or that exposes its own overridable
        accessors, as ``ReactAgent`` does) supplies them instead of this object
        recomputing — the DECISION stays in one place, which is the part that
        must not drift. Omitted, they are measured from these records.
        """
        cap = self.cap_usd
        if cap is None:
            return None

        if unpriced is None:
            unpriced = self.has_unpriced_records()
        # A cap we cannot measure is not a cap: an unpriced model keeps the
        # running total at $0.00 forever and the guard never fires — the same
        # silently-inert control, one layer down. Refuse before spending.
        if unpriced:
            return (
                f"A cost cap of ${cap:.2f} is configured, but spend cannot be "
                f"measured for {', '.join(sorted(self.models_used())) or 'this model'} "
                "— no pricing data. Remove the cap, or use a model with known pricing."
            )

        if spent is None:
            spent = self.prior_cost_usd + self.estimate_cost()
        if spent >= cap:
            return (
                f"Estimated spend ${spent:.4f} reached the configured cap of "
                f"${cap:.2f}. Raise 'Max cost per task (USD)' in Settings to continue."
            )
        return None

    def check(self) -> None:
        """Raise :class:`CostCapExceeded` when spending must stop."""
        message = self.cap_message()
        if message:
            raise CostCapExceeded(message)


def load_prior_task_cost(workspace, task_id: str) -> float:
    """Spend already recorded against ``task_id`` by earlier runs.

    The same query ``ReactAgent._load_prior_task_cost`` uses — the repository on
    a direct connection to the per-workspace db, which is where
    ``_persist_token_usage`` writes. Best effort: an unreadable row means "no
    prior spend" rather than blocking the run.
    """
    import sqlite3

    conn = None
    try:
        from codeframe.platform_store.repositories.token_repository import (
            TokenRepository,
        )

        conn = sqlite3.connect(str(workspace.db_path))
        summary = TokenRepository(sync_conn=conn).get_task_token_summary(task_id)
        return float(summary.get("total_cost_usd") or 0.0)
    except Exception as exc:  # pragma: no cover - accounting must not block a run
        logger.debug("Could not read prior spend for task %s: %s", task_id, exc)
        return 0.0
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
