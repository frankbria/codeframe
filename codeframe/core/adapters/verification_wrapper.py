"""Verification gate wrapper for agent adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from codeframe.core.adapters.agent_adapter import AgentAdapter, AgentEvent, AgentResult
from codeframe.core.gates import GateStatus
from codeframe.core.gates import run as run_gates
from codeframe.core.workspace import Workspace


class VerificationWrapper:
    """Wraps any AgentAdapter with post-execution verification gates.

    After the inner adapter completes, runs verification gates (pytest, ruff, etc.).
    If gates fail, re-invokes the adapter with error context for self-correction,
    up to max_correction_rounds times.

    This is the same self-correction loop that ReactAgent._run_final_verification()
    uses, but decoupled from any specific engine so it wraps any adapter.
    """

    def __init__(
        self,
        inner: AgentAdapter,
        workspace: Workspace,
        max_correction_rounds: int = 3,
        gate_names: Optional[list[str]] = None,
        verbose: bool = False,
    ) -> None:
        self._inner = inner
        self._workspace = workspace
        self._max_correction_rounds = max_correction_rounds
        self._gate_names = gate_names  # None = use default gates
        self._verbose = verbose

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

            # Gates failed -- build correction prompt and re-invoke
            if on_event:
                on_event(AgentEvent(
                    type="verification_failed",
                    data={
                        "round": round_num + 1,
                        "checks": len(gate_result.checks),
                    },
                ))

            error_summary = self._format_gate_errors(gate_result)
            correction_prompt = (
                f"{prompt}\n\n"
                f"## Verification Gate Failures (Correction Round {round_num + 1})\n\n"
                f"Your previous changes failed the following verification gates. "
                f"Fix these issues:\n\n{error_summary}"
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

        # All rounds exhausted, gates still failing
        error_summary = self._format_gate_errors(gate_result)
        return AgentResult(
            status="failed",
            output=result.output,
            error=(
                f"Verification gates still failing after "
                f"{self._max_correction_rounds} correction rounds:\n{error_summary}"
            ),
        )

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
