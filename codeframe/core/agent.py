"""Agent orchestrator for CodeFRAME v2.

Coordinates the full agent execution loop:
1. Load context for task
2. Generate implementation plan
3. Execute plan steps
4. Detect blockers when stuck
5. Run verification gates
6. Emit events throughout

This module is headless - no FastAPI or HTTP dependencies.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, Callable

from codeframe.core.workspace import Workspace
from codeframe.core.context import ContextLoader, TaskContext
from codeframe.core.planner import Planner, ImplementationPlan, PlanStep, StepType
from codeframe.core.executor import Executor, ExecutionResult, ExecutionStatus, StepResult
from codeframe.core.gates import run as run_gates, GateResult, GateStatus
from codeframe.core import tasks, blockers, events
from codeframe.core.tasks import Task, TaskStatus
from codeframe.core.blockers import BlockerStatus
from codeframe.core.events import EventType
from codeframe.adapters.llm import LLMProvider, Purpose


class AgentStatus(str, Enum):
    """Current status of the agent."""

    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    BLOCKED = "blocked"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class BlockerInfo:
    """Information about a detected blocker.

    Attributes:
        reason: Why the agent is blocked
        question: Question to ask the user
        context: Additional context about the blocker
        step_index: Which step caused the blocker (if any)
    """

    reason: str
    question: str
    context: str = ""
    step_index: Optional[int] = None


@dataclass
class AgentState:
    """Current state of the agent execution.

    Attributes:
        status: Current agent status
        task_id: Task being executed
        plan: Generated implementation plan
        current_step: Current step index (0-based)
        step_results: Results of executed steps
        blocker: Current blocker (if any)
        gate_results: Results of verification gates
        attempt_count: Number of execution attempts
        max_attempts: Maximum attempts before giving up
    """

    status: AgentStatus = AgentStatus.IDLE
    task_id: str = ""
    plan: Optional[ImplementationPlan] = None
    current_step: int = 0
    step_results: list[StepResult] = field(default_factory=list)
    blocker: Optional[BlockerInfo] = None
    gate_results: list[GateResult] = field(default_factory=list)
    attempt_count: int = 0
    max_attempts: int = 3

    def to_dict(self) -> dict:
        """Convert to dictionary for persistence."""
        return {
            "status": self.status.value,
            "task_id": self.task_id,
            "plan": self.plan.to_dict() if self.plan else None,
            "current_step": self.current_step,
            "step_results": [
                {
                    "step_index": r.step.index,
                    "status": r.status.value,
                    "output": r.output,
                    "error": r.error,
                }
                for r in self.step_results
            ],
            "blocker": {
                "reason": self.blocker.reason,
                "question": self.blocker.question,
                "context": self.blocker.context,
            } if self.blocker else None,
            "attempt_count": self.attempt_count,
        }


# Blocker detection thresholds
MAX_CONSECUTIVE_FAILURES = 3
MAX_STEP_RETRIES = 2


class Agent:
    """Orchestrates task execution through the full agent loop.

    The agent coordinates:
    - Context loading and planning
    - Step-by-step execution
    - Blocker detection and creation
    - Verification gate integration
    - State management for pause/resume
    """

    def __init__(
        self,
        workspace: Workspace,
        llm_provider: LLMProvider,
        max_context_tokens: int = 100_000,
        dry_run: bool = False,
        on_event: Optional[Callable[[str, dict], None]] = None,
    ):
        """Initialize the agent.

        Args:
            workspace: Target workspace
            llm_provider: LLM provider for planning and code generation
            max_context_tokens: Maximum tokens for context loading
            dry_run: If True, don't make actual changes
            on_event: Optional callback for agent events
        """
        self.workspace = workspace
        self.llm = llm_provider
        self.max_context_tokens = max_context_tokens
        self.dry_run = dry_run
        self.on_event = on_event

        self.state = AgentState()
        self.context: Optional[TaskContext] = None
        self.executor: Optional[Executor] = None

    def run(self, task_id: str) -> AgentState:
        """Run the agent on a task.

        This is the main entry point. It runs the full agent loop:
        1. Load context
        2. Plan implementation
        3. Execute steps
        4. Handle blockers and gates
        5. Complete or fail

        Args:
            task_id: Task to execute

        Returns:
            Final AgentState
        """
        self.state = AgentState(task_id=task_id, status=AgentStatus.IDLE)
        self._emit_event("agent_started", {"task_id": task_id})

        try:
            # Load context
            self._emit_event("loading_context", {"task_id": task_id})
            self.context = self._load_context(task_id)

            # Check for open blockers first
            if self.context.open_blockers:
                self._handle_existing_blockers()
                return self.state

            # Plan implementation
            self.state.status = AgentStatus.PLANNING
            self._emit_event("planning_started", {})
            self.state.plan = self._create_plan()
            self._emit_event("planning_completed", {
                "steps": self.state.plan.total_steps,
                "complexity": self.state.plan.estimated_complexity.value,
            })

            # Execute plan
            self.state.status = AgentStatus.EXECUTING
            self._execute_plan()

            # Run final verification if execution succeeded
            if self.state.status == AgentStatus.EXECUTING:
                self._run_final_verification()

        except Exception as e:
            self.state.status = AgentStatus.FAILED
            self._emit_event("agent_failed", {"error": str(e)})
            raise

        self._emit_event("agent_finished", {"status": self.state.status.value})
        return self.state

    def resume(self, task_id: str, state: AgentState) -> AgentState:
        """Resume execution from a saved state.

        Args:
            task_id: Task to resume
            state: Previous agent state

        Returns:
            Final AgentState
        """
        self.state = state
        self._emit_event("agent_resumed", {"task_id": task_id, "step": state.current_step})

        # Reload context
        self.context = self._load_context(task_id)

        # Check if blockers are now resolved
        if self.state.status == AgentStatus.BLOCKED:
            if not self.context.open_blockers:
                # Blockers resolved, continue execution
                self.state.status = AgentStatus.EXECUTING
                self.state.blocker = None
                self._execute_plan()
            else:
                # Still blocked
                return self.state

        # Run final verification if needed
        if self.state.status == AgentStatus.EXECUTING:
            self._run_final_verification()

        self._emit_event("agent_finished", {"status": self.state.status.value})
        return self.state

    def _load_context(self, task_id: str) -> TaskContext:
        """Load context for a task."""
        loader = ContextLoader(self.workspace, max_tokens=self.max_context_tokens)
        return loader.load(task_id)

    def _create_plan(self) -> ImplementationPlan:
        """Create implementation plan from context."""
        planner = Planner(self.llm)
        return planner.create_plan(self.context)

    def _execute_plan(self) -> None:
        """Execute the implementation plan step by step."""
        if not self.state.plan:
            raise ValueError("No plan to execute")

        self.executor = Executor(
            llm_provider=self.llm,
            repo_path=self.workspace.repo_path,
            dry_run=self.dry_run,
        )

        consecutive_failures = 0

        while self.state.current_step < len(self.state.plan.steps):
            step = self.state.plan.steps[self.state.current_step]

            self._emit_event("step_started", {
                "step": step.index,
                "type": step.type.value,
                "target": step.target,
            })

            # Execute the step
            result = self.executor.execute_step(step, self.context)
            self.state.step_results.append(result)

            if result.status == ExecutionStatus.SUCCESS:
                consecutive_failures = 0
                self._emit_event("step_completed", {
                    "step": step.index,
                    "output": result.output[:200],
                })

                # Run incremental verification for file changes
                if step.type in {StepType.FILE_CREATE, StepType.FILE_EDIT}:
                    gate_result = self._run_incremental_verification()
                    if gate_result and not gate_result.passed:
                        # Try to fix lint issues automatically
                        if not self._try_auto_fix(gate_result):
                            consecutive_failures += 1

                self.state.current_step += 1

            elif result.status == ExecutionStatus.FAILED:
                consecutive_failures += 1
                self._emit_event("step_failed", {
                    "step": step.index,
                    "error": result.error[:200],
                })

                # Check if we should create a blocker
                if self._should_create_blocker(consecutive_failures, result):
                    self._create_blocker_from_failure(step, result)
                    return

                # Try to recover or give up
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    self.state.status = AgentStatus.FAILED
                    self._emit_event("execution_failed", {
                        "reason": "Too many consecutive failures",
                    })
                    return

                self.state.current_step += 1  # Skip and continue

            elif result.status == ExecutionStatus.SKIPPED:
                self._emit_event("step_skipped", {"step": step.index})
                self.state.current_step += 1

    def _run_incremental_verification(self) -> Optional[GateResult]:
        """Run quick verification after file changes."""
        # Only run fast checks (ruff) for incremental verification
        try:
            result = run_gates(
                self.workspace,
                gates=["ruff"],
                verbose=False,
            )
            self.state.gate_results.append(result)
            return result
        except Exception:
            return None

    def _run_final_verification(self) -> None:
        """Run full verification gates at the end."""
        self.state.status = AgentStatus.VERIFYING
        self._emit_event("verification_started", {})

        try:
            result = run_gates(self.workspace, verbose=False)
            self.state.gate_results.append(result)

            if result.passed:
                self.state.status = AgentStatus.COMPLETED
                self._emit_event("verification_passed", {})
                # Note: task status update handled by runtime.complete_run()

            else:
                # Verification failed - create blocker or fail
                self.state.attempt_count += 1

                if self.state.attempt_count < self.state.max_attempts:
                    # Create blocker for human review
                    self._create_verification_blocker(result)
                else:
                    self.state.status = AgentStatus.FAILED
                    self._emit_event("verification_failed", {
                        "reason": "Max attempts exceeded",
                    })

        except Exception as e:
            self._emit_event("verification_error", {"error": str(e)})
            self.state.status = AgentStatus.COMPLETED  # Best effort

    def _try_auto_fix(self, gate_result: GateResult) -> bool:
        """Try to automatically fix lint issues.

        Returns:
            True if auto-fix was successful
        """
        # Try running ruff --fix
        if self.executor and not self.dry_run:
            import subprocess
            try:
                subprocess.run(
                    ["ruff", "check", "--fix", "."],
                    cwd=self.workspace.repo_path,
                    capture_output=True,
                    timeout=30,
                )
                return True
            except Exception:
                pass
        return False

    def _should_create_blocker(
        self,
        consecutive_failures: int,
        result: StepResult,
    ) -> bool:
        """Determine if we should create a blocker.

        Blockers are created when:
        - Multiple consecutive failures
        - Error suggests missing information
        - Error suggests ambiguous requirements
        """
        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            return True

        # Check for patterns suggesting human input needed
        error_lower = result.error.lower()
        needs_human_patterns = [
            "not found",
            "missing",
            "undefined",
            "unclear",
            "ambiguous",
            "permission denied",
            "authentication",
            "api key",
            "credentials",
        ]

        return any(pattern in error_lower for pattern in needs_human_patterns)

    def _create_blocker_from_failure(
        self,
        step: PlanStep,
        result: StepResult,
    ) -> None:
        """Create a blocker from a step failure."""
        question = self._generate_blocker_question(step, result)

        # Create blocker in database
        blocker = blockers.create(
            workspace=self.workspace,
            question=question,
            task_id=self.state.task_id,
        )

        self.state.status = AgentStatus.BLOCKED
        self.state.blocker = BlockerInfo(
            reason=result.error,
            question=question,
            context=f"Step {step.index}: {step.description}",
            step_index=step.index,
        )

        self._emit_event("blocker_created", {
            "blocker_id": blocker.id,
            "question": question,
        })

        # Update task status
        tasks.update_status(
            self.workspace,
            self.state.task_id,
            TaskStatus.BLOCKED,
        )

    def _create_verification_blocker(self, gate_result: GateResult) -> None:
        """Create a blocker from verification failure."""
        failed_checks = [
            c.name for c in gate_result.checks
            if c.status == GateStatus.FAILED
        ]

        question = (
            f"Verification failed for: {', '.join(failed_checks)}. "
            "Please review the changes and advise on how to fix the issues, "
            "or confirm the changes are acceptable."
        )

        blocker = blockers.create(
            workspace=self.workspace,
            question=question,
            task_id=self.state.task_id,
        )

        self.state.status = AgentStatus.BLOCKED
        self.state.blocker = BlockerInfo(
            reason="Verification failed",
            question=question,
            context=f"Failed checks: {failed_checks}",
        )

        self._emit_event("blocker_created", {
            "blocker_id": blocker.id,
            "question": question,
        })

        tasks.update_status(
            self.workspace,
            self.state.task_id,
            TaskStatus.BLOCKED,
        )

    def _generate_blocker_question(
        self,
        step: PlanStep,
        result: StepResult,
    ) -> str:
        """Generate a helpful question for the blocker."""
        # Use LLM to generate a clear question
        prompt = f"""A code execution step failed. Generate a clear, specific question to ask the user for help.

Step: {step.description}
Target: {step.target}
Error: {result.error}

Generate a single question that would help resolve this issue. Be specific about what information or decision is needed.
Question:"""

        try:
            response = self.llm.complete(
                messages=[{"role": "user", "content": prompt}],
                purpose=Purpose.GENERATION,
                max_tokens=200,
                temperature=0.0,
            )
            return response.content.strip()
        except Exception:
            # Fallback to generic question
            return f"Step '{step.description}' failed with error: {result.error}. How should I proceed?"

    def _handle_existing_blockers(self) -> None:
        """Handle situation where task already has open blockers."""
        self.state.status = AgentStatus.BLOCKED

        # Get the first open blocker
        open_blocker = self.context.open_blockers[0]
        self.state.blocker = BlockerInfo(
            reason="Pre-existing blocker",
            question=open_blocker.question,
        )

        self._emit_event("existing_blocker", {
            "blocker_id": open_blocker.id,
            "question": open_blocker.question,
        })

    def _emit_event(self, event_type: str, data: dict) -> None:
        """Emit an agent event."""
        if self.on_event:
            self.on_event(event_type, data)

        # Also emit to workspace event log
        try:
            events.emit_for_workspace(
                self.workspace,
                EventType.WORK_STARTED if event_type == "agent_started" else EventType.RUN_STEP,
                data={"agent_event": event_type, **data},
                print_event=False,
            )
        except Exception:
            pass  # Don't fail on event emission
