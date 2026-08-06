"""Builtin adapter shims wrapping ReactAgent and Agent behind AgentAdapter protocol.

These adapters encapsulate all engine-specific behavior (stall retry for React,
supervisor retry for Plan) so the runtime can treat all engines uniformly.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from codeframe.core.adapters.agent_adapter import (
    AdapterTokenUsage,
    AgentEvent,
    AgentResult,
)

if TYPE_CHECKING:
    from codeframe.adapters.llm.base import LLMProvider
    from codeframe.core.conductor import GlobalFixCoordinator
    from codeframe.core.stall_detector import StallAction
    from codeframe.core.streaming import EventPublisher, RunOutputLogger
    from codeframe.core.workspace import Workspace

logger = logging.getLogger(__name__)

_MAX_STALL_RETRIES = 1


def llm_key_requirement(repo_path: Optional[Path] = None) -> dict[str, str]:
    """The API key the *configured* LLM provider needs, if it needs one.

    Builtin engines call the LLM directly, so a hardcoded ``ANTHROPIC_API_KEY``
    made ``cf engines check react`` report the engine unready on an OpenAI or
    Ollama workspace — and ready on a machine that merely happens to have an
    Anthropic key exported while being configured for something else (#955).

    The provider comes from the standard chain (``CODEFRAME_LLM_PROVIDER`` →
    ``.codeframe/config.yaml`` → anthropic); ``repo_path`` is what enables the
    config tier. Local providers (ollama, vllm, compatible) need no key, so they
    report nothing to satisfy — which is what "Ready" should mean for them.
    """
    from codeframe.core.llm_resolution import REQUIRED_KEY_ENV, resolve_llm_settings

    try:
        provider = resolve_llm_settings(repo_path=repo_path).provider_type
    except Exception:  # noqa: BLE001 - see below
        # A requirements *check* must not be the thing that fails on a broken or
        # untrusted workspace config; the run itself reports that properly.
        provider = os.getenv("CODEFRAME_LLM_PROVIDER") or "anthropic"

    key = REQUIRED_KEY_ENV.get(provider)
    return {key: f"API key for the configured LLM provider ({provider})"} if key else {}


def _adapter_token_usage(agent: object) -> Optional[AdapterTokenUsage]:
    """Build AdapterTokenUsage from a builtin agent's accumulated records.

    Returns None when the agent recorded nothing — an absent figure is honest,
    a zero one claims the run was free. Never raises: token reporting must not
    be able to fail a run that already succeeded.
    """
    if agent is None:
        return None
    try:
        totals = agent.get_total_tokens()  # type: ignore[attr-defined]
        if not totals or not (totals.get("input_tokens") or totals.get("output_tokens")):
            return None
        records = agent.get_token_usage()  # type: ignore[attr-defined]
        models = {r.get("model") for r in records if r.get("model")}
        return AdapterTokenUsage(
            input_tokens=totals.get("input_tokens", 0),
            output_tokens=totals.get("output_tokens", 0),
            # Only name a model when the run used exactly one; a mixed run has
            # no single answer and guessing would mis-price it downstream.
            model=next(iter(models)) if len(models) == 1 else None,
            cost_usd=totals.get("estimated_cost_usd"),
        )
    except Exception:  # noqa: BLE001 - see docstring
        logger.warning("Could not read token usage from agent", exc_info=True)
        return None


class BuiltinReactAdapter:
    """Wraps the existing ReactAgent behind the AgentAdapter interface.

    Handles stall detection and retry internally so the runtime
    doesn't need engine-specific branching.
    """

    def __init__(
        self,
        workspace: Workspace,
        llm_provider: LLMProvider,
        *,
        stall_timeout_s: float = 300,
        stall_action: Optional[StallAction] = None,
        event_publisher: Optional[EventPublisher] = None,
        dry_run: bool = False,
        verbose: bool = False,
        debug: bool = False,
        output_logger: Optional[RunOutputLogger] = None,
        fix_coordinator: Optional[GlobalFixCoordinator] = None,
    ) -> None:
        self._workspace = workspace
        self._llm_provider = llm_provider
        self._stall_timeout_s = stall_timeout_s
        self._stall_action = stall_action
        self._event_publisher = event_publisher
        self._dry_run = dry_run
        self._verbose = verbose
        self._debug = debug
        self._output_logger = output_logger
        self._fix_coordinator = fix_coordinator

    @property
    def name(self) -> str:
        return "react"

    @classmethod
    def requirements(cls, repo_path: Optional[Path] = None) -> dict[str, str]:
        """Return requirement names and descriptions (#955: provider-aware)."""
        return llm_key_requirement(repo_path)

    def run(
        self,
        task_id: str,
        prompt: str,
        workspace_path: Path,
        on_event: Callable[[AgentEvent], None] | None = None,
    ) -> AgentResult:
        """Run the ReactAgent with stall retry, map AgentStatus to AgentResult."""
        from codeframe.core.react_agent import ReactAgent
        from codeframe.core.sandbox.context import rebased_workspace
        from codeframe.core.stall_detector import StallDetectedError

        # #715: when isolated in a worktree, run against workspace_path so code
        # I/O and gates land in the worktree; task/blocker state stays on the
        # main-repo DB (rebased_workspace keeps state_dir unchanged).
        run_workspace = rebased_workspace(self._workspace, workspace_path)

        def _bridge_event(event_type: str, data: dict) -> None:
            if on_event:
                on_event(AgentEvent(type=event_type, data=data))

        def _build_agent() -> ReactAgent:
            kwargs: dict = {
                "workspace": run_workspace,
                "llm_provider": self._llm_provider,
                "stall_timeout_s": self._stall_timeout_s,
                "event_publisher": self._event_publisher,
                "dry_run": self._dry_run,
                "verbose": self._verbose,
                "on_event": _bridge_event,
                "debug": self._debug,
                "output_logger": self._output_logger,
                "fix_coordinator": self._fix_coordinator,
            }
            if self._stall_action is not None:
                kwargs["stall_action"] = self._stall_action
            return ReactAgent(**kwargs)

        for stall_attempt in range(1 + _MAX_STALL_RETRIES):
            try:
                agent = _build_agent()
                status = agent.run(task_id)
                return self._map_status(status, agent)
            except StallDetectedError as exc:
                logger.warning(
                    "Stall detected (attempt %d): %s",
                    stall_attempt + 1, exc,
                )
                if stall_attempt >= _MAX_STALL_RETRIES:
                    logger.error("Max stall retries exceeded, failing task")
                    return AgentResult(
                        status="failed",
                        error=f"Stall detected after {stall_attempt + 1} attempts: {exc}",
                    )
                logger.info("Retrying after stall (attempt %d)", stall_attempt + 2)

        return AgentResult(status="failed", error="Unexpected: stall retry loop exhausted")

    @staticmethod
    def _map_status(status: object, agent: object = None) -> AgentResult:
        """Map AgentStatus enum to AgentResult, carrying the agent's token usage.

        The builtin engines are the *default*, and this used to drop the token
        counts on the floor — so engine stats and the Costs page reported 0 for
        every ordinary run while the delegated adapters reported real figures
        (#932). ReactAgent already accumulates the numbers.
        """
        from codeframe.core.agent import AgentStatus

        status_map = {
            AgentStatus.COMPLETED: "completed",
            AgentStatus.FAILED: "failed",
            AgentStatus.BLOCKED: "blocked",
        }
        result_status = status_map.get(status, "failed")  # type: ignore[arg-type]
        return AgentResult(
            status=result_status,
            output=f"ReactAgent finished with status: {status.value}",  # type: ignore[union-attr]
            token_usage=_adapter_token_usage(agent),
        )


class BuiltinPlanAdapter:
    """Wraps the existing plan-based Agent behind the AgentAdapter interface.

    Handles supervisor BLOCKED-retry and tactical failure recovery internally.
    """

    def __init__(
        self,
        workspace: Workspace,
        llm_provider: LLMProvider,
        *,
        dry_run: bool = False,
        verbose: bool = False,
        debug: bool = False,
        output_logger: Optional[RunOutputLogger] = None,
        fix_coordinator: Optional[GlobalFixCoordinator] = None,
        event_publisher: Optional[EventPublisher] = None,
    ) -> None:
        self._workspace = workspace
        self._llm_provider = llm_provider
        self._dry_run = dry_run
        self._verbose = verbose
        self._debug = debug
        self._output_logger = output_logger
        self._fix_coordinator = fix_coordinator
        self._event_publisher = event_publisher

    @property
    def name(self) -> str:
        return "plan"

    @classmethod
    def requirements(cls, repo_path: Optional[Path] = None) -> dict[str, str]:
        """Return requirement names and descriptions (#955: provider-aware)."""
        return llm_key_requirement(repo_path)

    def run(
        self,
        task_id: str,
        prompt: str,
        workspace_path: Path,
        on_event: Callable[[AgentEvent], None] | None = None,
    ) -> AgentResult:
        """Run the plan-based Agent with supervisor retry, map to AgentResult."""
        from codeframe.core.agent import Agent, AgentStatus
        from codeframe.core.sandbox.context import rebased_workspace

        # #715: run against the worktree path when isolated (state stays on main).
        run_workspace = rebased_workspace(self._workspace, workspace_path)

        def _bridge_event(event_type: str, data: dict) -> None:
            if on_event:
                on_event(AgentEvent(type=event_type, data=data))

        def _build_agent() -> Agent:
            return Agent(
                workspace=run_workspace,
                llm_provider=self._llm_provider,
                dry_run=self._dry_run,
                on_event=_bridge_event,
                debug=self._debug,
                verbose=self._verbose,
                fix_coordinator=self._fix_coordinator,
                output_logger=self._output_logger,
                event_publisher=self._event_publisher,
            )

        agent = _build_agent()
        state = agent.run(task_id)

        # Supervisor BLOCKED-retry (best-effort — failures don't affect result)
        if state.status == AgentStatus.BLOCKED:
            try:
                state = self._try_supervisor_unblock(state, task_id, _build_agent)
            except Exception:
                logger.debug("Supervisor unblock failed, returning original state", exc_info=True)

        # Supervisor tactical failure recovery (best-effort)
        if state.status == AgentStatus.FAILED:
            try:
                state = self._try_tactical_recovery(state, task_id, _build_agent)
            except Exception:
                logger.debug("Supervisor tactical recovery failed, returning original state", exc_info=True)

        return self._map_state(state)

    def _try_supervisor_unblock(self, state, task_id: str, build_agent):
        """Try supervisor resolution for BLOCKED tasks."""
        from codeframe.core.conductor import get_supervisor

        supervisor = get_supervisor(self._workspace)
        if supervisor.try_resolve_blocked_task(task_id):
            logger.info("[Supervisor] Retrying task after auto-resolution...")
            agent = build_agent()
            state = agent.run(task_id)
        return state

    def _try_tactical_recovery(self, state, task_id: str, build_agent):
        """Try supervisor tactical recovery for FAILED tasks."""
        from codeframe.core.conductor import get_supervisor, SUPERVISOR_TACTICAL_PATTERNS

        error_msg = self._extract_error(state)

        if not error_msg:
            return state

        error_msg_lower = error_msg.lower()
        matched_patterns = [p for p in SUPERVISOR_TACTICAL_PATTERNS if p in error_msg_lower]

        if not matched_patterns:
            return state

        supervisor = get_supervisor(self._workspace)
        resolution = supervisor._generate_tactical_resolution(error_msg)
        logger.info(
            "Supervisor detected recoverable error, providing guidance: %s...",
            resolution[:100],
        )

        from codeframe.core import blockers
        blocker = blockers.create(
            self._workspace,
            task_id=task_id,
            question=f"Technical error: {error_msg[:500]}",
            created_by="agent",
        )
        blockers.answer(self._workspace, blocker.id, resolution)

        logger.info("Supervisor retrying task with guidance...")
        agent = build_agent()
        return agent.run(task_id)

    @staticmethod
    def _extract_error(state) -> str:
        """Extract error message from AgentState for supervisor analysis."""
        blocker = getattr(state, "blocker", None)
        if blocker:
            return getattr(blocker, "reason", None) or getattr(blocker, "question", None) or ""

        step_results = getattr(state, "step_results", None) or []
        if step_results:
            last_result = step_results[-1]
            if hasattr(last_result, "error") and last_result.error:
                return last_result.error
            if hasattr(last_result, "output") and last_result.output:
                return last_result.output

        gate_results = getattr(state, "gate_results", None) or []
        for gate in gate_results:
            if not gate.passed:
                for check in gate.checks:
                    if check.output:
                        return check.output

        return ""

    @staticmethod
    def _map_state(state: object) -> AgentResult:
        """Map AgentState dataclass to AgentResult."""
        from codeframe.core.agent import AgentStatus

        status_map = {
            AgentStatus.COMPLETED: "completed",
            AgentStatus.FAILED: "failed",
            AgentStatus.BLOCKED: "blocked",
        }
        result_status = status_map.get(state.status, "failed")  # type: ignore[union-attr]

        blocker_question = None
        if state.status == AgentStatus.BLOCKED:  # type: ignore[union-attr]
            blocker = getattr(state, "blocker", None)
            if blocker:
                blocker_question = getattr(blocker, "question", None) or getattr(
                    blocker, "reason", None
                )

        error = None
        if state.status == AgentStatus.FAILED:  # type: ignore[union-attr]
            gate_results = getattr(state, "gate_results", None) or []
            error_parts: list[str] = []
            for gr in gate_results:
                for check in getattr(gr, "checks", []):
                    output = getattr(check, "output", None)
                    if output:
                        error_parts.append(output)
            if error_parts:
                error = "\n".join(error_parts[:3])

        return AgentResult(
            status=result_status,
            output=f"PlanAgent finished with status: {state.status.value}",  # type: ignore[union-attr]
            blocker_question=blocker_question,
            error=error,
        )
