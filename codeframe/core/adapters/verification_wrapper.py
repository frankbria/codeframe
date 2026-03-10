"""Verification gate wrapper for agent adapters.

Wraps any AgentAdapter with post-execution verification gates, quick fixes,
fix attempt tracking, and escalation to blockers. This gives all execution
engines (built-in and external) the same self-correction capabilities that
ReactAgent has internally.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from codeframe.core.adapters.agent_adapter import AgentAdapter, AgentEvent, AgentResult
from codeframe.core import blockers
from codeframe.core.fix_tracker import (
    EscalationDecision,
    FixAttemptTracker,
    FixOutcome,
    build_escalation_question,
)
from codeframe.core.gates import GateStatus
from codeframe.core.gates import run as run_gates
from codeframe.core.quick_fixes import apply_quick_fix, find_quick_fix
from codeframe.core.workspace import Workspace

logger = logging.getLogger(__name__)


class VerificationWrapper:
    """Wraps any AgentAdapter with post-execution verification gates.

    After the inner adapter completes, runs verification gates (pytest, ruff, etc.).
    If gates fail:
    1. Try a pattern-based quick fix (no LLM needed)
    2. If quick fix applied, re-run gates immediately
    3. If no quick fix, re-invoke adapter with error context for self-correction
    4. Track all fix attempts to detect loops
    5. Escalate to blocker when fix tracker recommends it or retries exhausted

    This is the same self-correction pattern that ReactAgent._run_final_verification()
    uses, but decoupled from any specific engine so it wraps any adapter.
    """

    def __init__(
        self,
        inner: AgentAdapter,
        workspace: Workspace,
        max_correction_rounds: int = 5,
        gate_names: Optional[list[str]] = None,
        verbose: bool = False,
    ) -> None:
        self._inner = inner
        self._workspace = workspace
        self._max_correction_rounds = max_correction_rounds
        self._gate_names = gate_names  # None = use default gates
        self._verbose = verbose
        self.fix_tracker = FixAttemptTracker()

    @property
    def name(self) -> str:
        return f"verified-{self._inner.name}"

    def run(
        self,
        task_id: str,
        prompt: str,
        workspace_path: Path,
        on_event: Callable[[AgentEvent], None] | None = None,
    ) -> AgentResult:
        """Run the inner adapter, then verify with gates. Self-correct on failure."""

        # Initial run
        result = self._inner.run(task_id, prompt, workspace_path, on_event)

        # Only verify if the adapter reported success
        if result.status != "completed":
            return result

        # Run verification gates with self-correction loop
        for round_num in range(self._max_correction_rounds):
            if on_event:
                on_event(AgentEvent(
                    type="verification",
                    data={
                        "round": round_num + 1,
                        "max_rounds": self._max_correction_rounds,
                    },
                ))

            gate_result = run_gates(
                self._workspace,
                gates=self._gate_names,
                verbose=self._verbose,
            )

            if gate_result.passed:
                if on_event:
                    on_event(AgentEvent(type="verification_passed", data={}))
                return result

            # Gates failed — get structured error summary
            error_summary = (
                gate_result.get_error_summary() or
                self._format_gate_errors(gate_result)
            )

            if on_event:
                on_event(AgentEvent(
                    type="verification_failed",
                    data={
                        "round": round_num + 1,
                        "checks": len(gate_result.checks),
                    },
                ))

            # 1. Record the attempt (outcome deferred until we know if fix works)
            self.fix_tracker.record_attempt(error_summary, "verification_gate")

            # 2. Check escalation based on prior history
            escalation = self.fix_tracker.should_escalate(error_summary)
            if escalation.should_escalate:
                self.fix_tracker.record_outcome(
                    error_summary, "verification_gate", FixOutcome.FAILED,
                )
                return self._create_escalation_blocker(
                    task_id, error_summary, escalation,
                    last_output=result.output,
                )

            # 3. Try quick fix first (no adapter re-invocation needed)
            if self._try_quick_fix(error_summary):
                self.fix_tracker.record_outcome(
                    error_summary, "verification_gate", FixOutcome.SUCCESS,
                )
                self._verbose_print(
                    f"[VerificationWrapper] Quick fix applied (round {round_num + 1})"
                )
                continue  # Re-run gates without re-invoking adapter

            # 4. No quick fix — record failure and re-invoke adapter with error context
            self.fix_tracker.record_outcome(
                error_summary, "verification_gate", FixOutcome.FAILED,
            )
            formatted_errors = self._format_gate_errors(gate_result)
            correction_prompt = (
                f"{prompt}\n\n"
                f"## Verification Gate Failures (Correction Round {round_num + 1})\n\n"
                f"Your previous changes failed the following verification gates. "
                f"Fix these issues:\n\n{formatted_errors}"
            )

            result = self._inner.run(
                task_id, correction_prompt, workspace_path, on_event,
            )

            if result.status != "completed":
                return result

        # Final gate check after all correction rounds
        gate_result = run_gates(
            self._workspace,
            gates=self._gate_names,
            verbose=self._verbose,
        )

        if gate_result.passed:
            return result

        # All rounds exhausted — create blocker
        error_summary = self._format_gate_errors(gate_result)
        return self._create_exhaustion_blocker(
            task_id, error_summary, last_output=result.output,
        )

    def _try_quick_fix(self, error_summary: str) -> bool:
        """Attempt a pattern-based quick fix for the gate error.

        Returns True if a fix was successfully applied.
        """
        fix = find_quick_fix(error_summary, repo_path=self._workspace.repo_path)
        if fix is None:
            return False

        success, msg = apply_quick_fix(fix, self._workspace.repo_path)
        if success:
            self._verbose_print(f"[VerificationWrapper] Quick fix: {msg}")
        return success

    def _create_escalation_blocker(
        self,
        task_id: str,
        error: str,
        escalation: EscalationDecision,
        last_output: str = "",
    ) -> AgentResult:
        """Create a blocker when fix tracker recommends escalation."""
        question = build_escalation_question(
            error, escalation.reason, self.fix_tracker,
        )

        try:
            blockers.create(
                workspace=self._workspace,
                question=question,
                task_id=task_id,
            )
        except Exception:
            logger.warning("Failed to create escalation blocker", exc_info=True)

        return AgentResult(
            status="blocked",
            output=last_output,
            blocker_question=question,
            error=f"Escalated to blocker: {escalation.reason}",
        )

    def _create_exhaustion_blocker(
        self,
        task_id: str,
        error_summary: str,
        last_output: str = "",
    ) -> AgentResult:
        """Create a blocker when all correction rounds are exhausted."""
        question = (
            f"Verification gates still failing after "
            f"{self._max_correction_rounds} correction rounds.\n\n"
            f"Errors:\n{error_summary[:500]}\n\n"
            f"Please investigate and provide guidance."
        )

        try:
            blockers.create(
                workspace=self._workspace,
                question=question,
                task_id=task_id,
            )
        except Exception:
            logger.warning("Failed to create exhaustion blocker", exc_info=True)

        return AgentResult(
            status="blocked",
            output=last_output,
            blocker_question=question,
            error=(
                f"Verification gates still failing after "
                f"{self._max_correction_rounds} correction rounds:\n{error_summary}"
            ),
        )

    def _verbose_print(self, msg: str) -> None:
        if self._verbose:
            print(msg)

    @staticmethod
    def _format_gate_errors(gate_result) -> str:
        """Format gate check failures into a readable summary."""

        lines: list[str] = []
        for check in gate_result.checks:
            if check.status == GateStatus.FAILED:
                lines.append(f"### {check.name}: FAILED")
                if check.output:
                    lines.append(f"```\n{check.output[:2000]}\n```")
                lines.append("")
        return "\n".join(lines) if lines else "Gate checks failed (no details available)"
