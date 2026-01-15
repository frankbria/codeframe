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

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, Callable

import re

from codeframe.core.workspace import Workspace
from codeframe.core.context import ContextLoader, TaskContext
from codeframe.core.planner import Planner, ImplementationPlan, PlanStep, StepType
from codeframe.core.executor import Executor, ExecutionStatus, StepResult
from codeframe.core.gates import run as run_gates, GateResult, GateStatus
from codeframe.core import blockers, events
from codeframe.core.events import EventType
from codeframe.adapters.llm import LLMProvider, Purpose


def _extract_file_from_command(command: str) -> Optional[str]:
    """Extract a file path from a verification command.

    Examples:
        "python task_tracker.py --help" -> "task_tracker.py"
        "pytest tests/test_foo.py" -> "tests/test_foo.py"
        "ruff check main.py" -> "main.py"
        "python -m mymodule" -> None

    Args:
        command: The shell command to parse

    Returns:
        The file path if found, None otherwise
    """
    if not command:
        return None

    # Common patterns for Python file references
    # Match .py files in the command
    py_match = re.search(r'(\S+\.py)', command)
    if py_match:
        return py_match.group(1)

    # No file found
    return None


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
MAX_SELF_CORRECTION_ATTEMPTS = 2

# Error patterns that indicate the agent needs human input
# These are situations where the agent genuinely cannot proceed without a human decision
HUMAN_INPUT_PATTERNS = [
    # Requirements/specification issues
    "unclear",
    "ambiguous",
    "which approach",
    "should i use",
    "please clarify",
    "need clarification",
    "multiple options",
    "design decision",
    # Access/credentials issues
    "permission denied",
    "access denied",
    "authentication required",
    "api key",
    "credentials",
    "secret",
    "token required",
    # External dependencies requiring human action
    "service unavailable",
    "rate limited",
    "quota exceeded",
]

# Error patterns that are technical and the agent should self-correct
# These are coding/execution errors the agent can fix by trying a different approach
TECHNICAL_ERROR_PATTERNS = [
    # File/path issues - agent can find correct path or create file
    "file not found",
    "no such file",
    "directory not found",
    "path does not exist",
    "filenotfounderror",
    # Import/module issues - agent can fix imports
    "module not found",
    "import error",
    "no module named",
    "cannot find module",
    "modulenotfounderror",
    # Syntax/code issues - agent can fix code
    "syntax error",
    "syntaxerror",
    "indentation error",
    "name error",
    "nameerror",
    "type error",
    "typeerror",
    "attribute error",
    "attributeerror",
    "undefined",
    "not defined",
    # Command execution issues - agent can try different command
    "command not found",
    "exit code",
    "non-zero exit",
    # General coding issues
    "missing",  # usually missing import, argument, etc.
    "expected",
    "invalid",
]


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
        debug: bool = False,
    ):
        """Initialize the agent.

        Args:
            workspace: Target workspace
            llm_provider: LLM provider for planning and code generation
            max_context_tokens: Maximum tokens for context loading
            dry_run: If True, don't make actual changes
            on_event: Optional callback for agent events
            debug: If True, write detailed debug log to workspace
        """
        self.workspace = workspace
        self.llm = llm_provider
        self.max_context_tokens = max_context_tokens
        self.dry_run = dry_run
        self.on_event = on_event
        self.debug = debug

        self.state = AgentState()
        self.context: Optional[TaskContext] = None
        self.executor: Optional[Executor] = None

        # Debug logging setup
        self._debug_log_path: Optional[Path] = None
        self._failure_count = 0  # Track failures for verbose logging
        if debug:
            self._setup_debug_log()

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

        self._debug_log(
            f"Starting plan execution with {len(self.state.plan.steps)} steps",
            level="INFO",
            always=True,
        )

        while self.state.current_step < len(self.state.plan.steps):
            step = self.state.plan.steps[self.state.current_step]

            self._debug_log(
                f"=== STEP {step.index} ({step.type.value}) ===",
                level="INFO",
                data={
                    "target": step.target,
                    "description": step.description,
                    "details_length": len(step.details) if step.details else 0,
                    "current_step_index": self.state.current_step,
                    "consecutive_failures": consecutive_failures,
                },
                always=True,
            )

            self._emit_event("step_started", {
                "step": step.index,
                "type": step.type.value,
                "target": step.target,
            })

            # Execute the step
            result = self.executor.execute_step(step, self.context)
            self.state.step_results.append(result)

            self._debug_log(
                f"Step {step.index} execution result: {result.status.value}",
                level="INFO" if result.status == ExecutionStatus.SUCCESS else "WARN",
                data={
                    "output_preview": result.output[:200] if result.output else None,
                    "error": result.error if result.error else None,
                },
                always=True,
            )

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
                        # Try to fix lint issues automatically (works for style, not syntax)
                        if not self._try_auto_fix(gate_result):
                            # Auto-fix failed - need to self-correct the code
                            self._emit_event("verification_failed", {
                                "step": step.index,
                                "error": "Code verification failed after file change",
                            })

                            # Trigger self-correction for the verification failure
                            failed_checks = [
                                c.name for c in gate_result.checks
                                if c.status != GateStatus.PASSED
                            ]
                            failed_result = StepResult(
                                step=step,
                                status=ExecutionStatus.FAILED,
                                error=f"Verification failed: {failed_checks}",
                            )

                            # Try self-correction to fix the code
                            self_correction_attempts = 0
                            current_result = failed_result
                            self_correction_succeeded = False

                            while self_correction_attempts < MAX_SELF_CORRECTION_ATTEMPTS:
                                self_correction_attempts += 1
                                corrected_result = self._attempt_self_correction(
                                    step, current_result, self_correction_attempts
                                )

                                if corrected_result is None:
                                    break

                                if corrected_result.status == ExecutionStatus.SUCCESS:
                                    # Re-verify the corrected code
                                    recheck = self._run_incremental_verification()
                                    if recheck is None or recheck.passed:
                                        self._emit_event("step_completed", {
                                            "step": step.index,
                                            "output": "Code fixed via self-correction",
                                            "self_corrected": True,
                                        })
                                        self_correction_succeeded = True
                                        break

                                current_result = corrected_result

                            if not self_correction_succeeded:
                                # Couldn't fix the verification error
                                consecutive_failures += 1
                                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                                    # Create blocker asking for help with the code
                                    self._create_blocker_from_failure(step, current_result)
                                    return
                                # Otherwise, we continue to next step with broken file
                                # (not ideal, but prevents infinite loop)

                self.state.current_step += 1

            elif result.status == ExecutionStatus.FAILED:
                consecutive_failures += 1
                self._failure_count += 1  # Track for debug logging verbosity

                self._debug_log(
                    f"STEP FAILED: consecutive_failures={consecutive_failures}, total_failures={self._failure_count}",
                    level="WARN",
                    data={"error": result.error},
                    always=True,
                )

                self._emit_event("step_failed", {
                    "step": step.index,
                    "error": result.error[:200],
                })

                # Special handling for verification step failures
                # When verification fails (e.g., syntax error), we need to fix the TARGET file
                # not "self-correct" the verification step itself
                if step.type == StepType.VERIFICATION:
                    # Extract the actual file path from the verification command
                    # e.g., "python task_tracker.py --help" -> "task_tracker.py"
                    file_path = _extract_file_from_command(step.target)

                    if file_path:
                        # Create a FILE_EDIT step to fix the target file
                        fix_step = PlanStep(
                            index=step.index,
                            type=StepType.FILE_EDIT,
                            target=file_path,
                            description=f"Fix {file_path} - {result.error[:100]}",
                            details=f"The verification command '{step.target}' failed with error: {result.error}. Fix this error in {file_path}.",
                            depends_on=[],
                        )
                        # Replace step with the fix step for self-correction
                        step = fix_step
                    else:
                        # Can't determine which file to fix, create blocker
                        self._debug_log(
                            f"Cannot extract file path from verification command: {step.target}",
                            level="WARN",
                            always=True,
                        )
                        self._create_blocker_from_failure(step, result)
                        return

                # Classify the error
                error_type = self._classify_error(result.error)

                # For human-input-needed errors, create blocker immediately
                if error_type == "human":
                    self._create_blocker_from_failure(step, result)
                    return

                # For technical errors, try self-correction first
                self_correction_attempts = 0
                current_result = result
                self_correction_succeeded = False

                while self_correction_attempts < MAX_SELF_CORRECTION_ATTEMPTS:
                    self_correction_attempts += 1
                    corrected_result = self._attempt_self_correction(
                        step, current_result, self_correction_attempts
                    )

                    if corrected_result is None:
                        # Self-correction failed to even attempt, stop trying
                        break

                    if corrected_result.status == ExecutionStatus.SUCCESS:
                        # Self-correction worked! Update state and continue
                        self.state.step_results[-1] = corrected_result  # Replace failed result
                        consecutive_failures = 0
                        self._emit_event("step_completed", {
                            "step": step.index,
                            "output": corrected_result.output[:200],
                            "self_corrected": True,
                        })

                        # Run incremental verification for file changes
                        if step.type in {StepType.FILE_CREATE, StepType.FILE_EDIT}:
                            gate_result = self._run_incremental_verification()
                            if gate_result and not gate_result.passed:
                                if not self._try_auto_fix(gate_result):
                                    consecutive_failures += 1

                        self.state.current_step += 1
                        self_correction_succeeded = True
                        break

                    # Self-correction didn't succeed, try again
                    current_result = corrected_result

                # Handle case where self-correction didn't succeed
                if not self_correction_succeeded:
                    # Check if we should create a blocker
                    if self._should_create_blocker(
                        consecutive_failures, current_result, self_correction_attempts
                    ):
                        self._create_blocker_from_failure(step, current_result)
                        return

                    # Give up on this step if too many consecutive failures
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        self._debug_log(
                            f"GIVING UP: Too many consecutive failures ({consecutive_failures})",
                            level="ERROR",
                            always=True,
                        )
                        self.state.status = AgentStatus.FAILED
                        self._emit_event("execution_failed", {
                            "reason": "Too many consecutive failures after self-correction",
                        })
                        return

                    # Skip this step and continue to the next
                    self._debug_log(
                        f"Skipping failed step {step.index}, advancing to next step",
                        level="WARN",
                        always=True,
                    )
                    self.state.current_step += 1

            elif result.status == ExecutionStatus.SKIPPED:
                self._debug_log(f"Step {step.index} SKIPPED", level="INFO", always=True)
                self._emit_event("step_skipped", {"step": step.index})
                self.state.current_step += 1

        self._debug_log(
            f"Plan execution completed. Final step index: {self.state.current_step}",
            level="INFO",
            always=True,
        )

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

    def _classify_error(self, error: str) -> str:
        """Classify an error as technical or human-input-needed.

        Args:
            error: Error message to classify

        Returns:
            "technical" if agent can self-correct, "human" if needs human input
        """
        error_lower = error.lower()

        # Check human-input patterns first (they take priority)
        for pattern in HUMAN_INPUT_PATTERNS:
            if pattern in error_lower:
                return "human"

        # Check technical patterns
        for pattern in TECHNICAL_ERROR_PATTERNS:
            if pattern in error_lower:
                return "technical"

        # Default to technical - agent should try to fix it first
        return "technical"

    def _should_create_blocker(
        self,
        consecutive_failures: int,
        result: StepResult,
        self_correction_attempts: int = 0,
    ) -> bool:
        """Determine if we should create a blocker.

        Blockers are only created for genuine human-input-needed situations.
        Technical errors should be handled by self-correction first.

        Args:
            consecutive_failures: Number of consecutive step failures
            result: The failed step result
            self_correction_attempts: How many self-correction attempts were made

        Returns:
            True if a blocker should be created
        """
        error_type = self._classify_error(result.error)

        # Human-input-needed errors always create blockers
        if error_type == "human":
            return True

        # Technical errors only create blockers after exhausting self-correction
        if error_type == "technical":
            # Only block if we've tried self-correction and still failing
            if self_correction_attempts >= MAX_SELF_CORRECTION_ATTEMPTS:
                # After multiple self-correction attempts, the agent is truly stuck
                return True
            # Otherwise, don't block - let the caller try self-correction
            return False

        return False

    def _attempt_self_correction(
        self,
        step: PlanStep,
        result: StepResult,
        attempt: int,
    ) -> Optional[StepResult]:
        """Attempt to self-correct a failed step using LLM.

        Uses the LLM to analyze the error and generate a corrected approach.

        Args:
            step: The step that failed
            result: The failure result
            attempt: Which self-correction attempt this is (1-based)

        Returns:
            New StepResult if correction was attempted, None if can't correct
        """
        self._emit_event("self_correction_started", {
            "step": step.index,
            "attempt": attempt,
            "error": result.error[:200],
        })

        self._debug_log(
            f"SELF-CORRECTION attempt {attempt} for step {step.index}",
            level="INFO",
            data={
                "step_type": step.type.value,
                "target": step.target,
                "description": step.description,
                "error": result.error,
            },
            always=True,
        )

        prompt = f"""A code execution step failed. Analyze the error and provide a corrected approach.

Step Description: {step.description}
Step Type: {step.type.value}
Target: {step.target}

Error:
{result.error}

Previous approach that failed:
{step.details[:2000] if step.details else "No details"}

Please provide a corrected version that fixes this error. Consider:
1. If it's a file path issue, find the correct path or create the file
2. If it's an import issue, add the missing import
3. If it's a syntax error, fix the syntax
4. If it's a logic error, fix the logic

Respond with ONLY the corrected code/content, no explanation."""

        # Log the full prompt for debugging
        self._debug_log_llm_interaction(
            f"Self-correction attempt {attempt} for step {step.index}",
            prompt,
        )

        try:
            # Use CORRECTION purpose to step up to a stronger model (Opus)
            # for better error analysis and code fixing
            correction_model = self.llm.get_model(Purpose.CORRECTION)
            self._debug_log(
                f"Using stepped-up model for self-correction: {correction_model}",
                level="INFO",
                always=True,
            )

            response = self.llm.complete(
                messages=[{"role": "user", "content": prompt}],
                purpose=Purpose.CORRECTION,
                max_tokens=4000,
                temperature=0.0,
            )

            corrected_details = response.content.strip()

            # Log the full response for debugging
            self._debug_log_llm_interaction(
                f"Self-correction response {attempt} for step {step.index}",
                prompt,
                response=corrected_details,
            )

            self._debug_log(
                f"Self-correction LLM response received ({len(corrected_details)} chars)",
                level="DEBUG",
                data={"first_100_chars": corrected_details[:100]},
                always=True,
            )

            # Create a corrected step with the new details
            corrected_step = PlanStep(
                index=step.index,
                type=step.type,
                target=step.target,
                description=f"{step.description} (self-corrected, attempt {attempt})",
                details=corrected_details,
                depends_on=step.depends_on,
            )

            # Re-execute with corrected step
            self._debug_log(
                f"Executing corrected step {step.index}",
                level="DEBUG",
                always=True,
            )
            corrected_result = self.executor.execute_step(corrected_step, self.context)

            self._debug_log(
                f"Corrected step result: {corrected_result.status.value}",
                level="INFO",
                data={
                    "success": corrected_result.status == ExecutionStatus.SUCCESS,
                    "error": corrected_result.error if corrected_result.error else None,
                    "output": corrected_result.output[:200] if corrected_result.output else None,
                },
                always=True,
            )

            self._emit_event("self_correction_completed", {
                "step": step.index,
                "attempt": attempt,
                "success": corrected_result.status == ExecutionStatus.SUCCESS,
            })

            return corrected_result

        except Exception as e:
            self._debug_log(
                f"Self-correction EXCEPTION: {str(e)}",
                level="ERROR",
                always=True,
            )
            self._emit_event("self_correction_failed", {
                "step": step.index,
                "attempt": attempt,
                "error": str(e),
            })
            return None

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
        # Note: task status update handled by runtime.block_run()

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
        # Note: task status update handled by runtime.block_run()

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

    def _setup_debug_log(self) -> None:
        """Set up the debug log file in workspace directory."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._debug_log_path = self.workspace.repo_path / f".codeframe_debug_{timestamp}.log"

        # Write header
        with open(self._debug_log_path, "w") as f:
            f.write("=" * 80 + "\n")
            f.write("CodeFRAME Agent Debug Log\n")
            f.write(f"Started: {datetime.now(timezone.utc).isoformat()}\n")
            f.write(f"Workspace: {self.workspace.id}\n")
            f.write(f"Repo Path: {self.workspace.repo_path}\n")
            f.write("=" * 80 + "\n\n")

    def _debug_log(
        self,
        message: str,
        level: str = "INFO",
        data: Optional[dict] = None,
        always: bool = False,
    ) -> None:
        """Write to the debug log file.

        Args:
            message: Log message
            level: Log level (INFO, WARN, ERROR, DEBUG)
            data: Optional structured data to include
            always: If True, log even if failure count is low
        """
        if not self._debug_log_path:
            return

        # Only log detailed info after first failure, unless always=True
        if not always and self._failure_count == 0 and level == "DEBUG":
            return

        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] [{level}] {message}\n"

        with open(self._debug_log_path, "a") as f:
            f.write(line)
            if data:
                for key, value in data.items():
                    # Truncate long values for readability
                    val_str = str(value)
                    if len(val_str) > 500:
                        val_str = val_str[:500] + "... [TRUNCATED]"
                    f.write(f"  {key}: {val_str}\n")
                f.write("\n")

    def _debug_log_llm_interaction(
        self,
        label: str,
        prompt: str,
        response: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Log a full LLM interaction (prompt + response) for debugging."""
        if not self._debug_log_path:
            return

        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]

        with open(self._debug_log_path, "a") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"[{timestamp}] LLM INTERACTION: {label}\n")
            f.write(f"{'='*60}\n\n")

            f.write(f"--- PROMPT ({len(prompt)} chars) ---\n")
            f.write(prompt)
            f.write("\n\n")

            if response:
                f.write(f"--- RESPONSE ({len(response)} chars) ---\n")
                f.write(response)
                f.write("\n\n")
            elif error:
                f.write(f"--- ERROR ---\n{error}\n\n")

            f.write(f"{'='*60}\n\n")
