"""Builtin adapter shims wrapping ReactAgent and Agent behind AgentAdapter protocol."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from codeframe.core.adapters.agent_adapter import AgentEvent, AgentResult

if TYPE_CHECKING:
    from codeframe.adapters.llm.base import LLMProvider
    from codeframe.core.conductor import GlobalFixCoordinator
    from codeframe.core.stall_detector import StallAction
    from codeframe.core.streaming import EventPublisher, RunOutputLogger
    from codeframe.core.workspace import Workspace


class BuiltinReactAdapter:
    """Wraps the existing ReactAgent behind the AgentAdapter interface.

    This shim allows the ReactAgent to be used through the unified
    engine registry without modifying the ReactAgent class itself.
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

    def run(
        self,
        task_id: str,
        prompt: str,
        workspace_path: Path,
        on_event: Callable[[AgentEvent], None] | None = None,
    ) -> AgentResult:
        """Run the ReactAgent and map its AgentStatus to AgentResult."""
        from codeframe.core.react_agent import ReactAgent

        def _bridge_event(event_type: str, data: dict) -> None:
            if on_event:
                on_event(AgentEvent(type=event_type, data=data))

        kwargs: dict = {
            "workspace": self._workspace,
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

        agent = ReactAgent(**kwargs)
        status = agent.run(task_id)
        return self._map_status(status)

    @staticmethod
    def _map_status(status: object) -> AgentResult:
        """Map AgentStatus enum to AgentResult."""
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
        )


class BuiltinPlanAdapter:
    """Wraps the existing plan-based Agent behind the AgentAdapter interface."""

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

    def run(
        self,
        task_id: str,
        prompt: str,
        workspace_path: Path,
        on_event: Callable[[AgentEvent], None] | None = None,
    ) -> AgentResult:
        """Run the plan-based Agent and map its AgentState to AgentResult."""
        from codeframe.core.agent import Agent

        def _bridge_event(event_type: str, data: dict) -> None:
            if on_event:
                on_event(AgentEvent(type=event_type, data=data))

        agent = Agent(
            workspace=self._workspace,
            llm_provider=self._llm_provider,
            dry_run=self._dry_run,
            on_event=_bridge_event,
            debug=self._debug,
            verbose=self._verbose,
            fix_coordinator=self._fix_coordinator,
            output_logger=self._output_logger,
            event_publisher=self._event_publisher,
        )
        state = agent.run(task_id)
        return self._map_state(state)

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
