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

import re
import shlex
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from codeframe.adapters.llm import LLMProvider, Purpose
from codeframe.core import blockers, events
from codeframe.core.context import ContextLoader, TaskContext
from codeframe.core.events import EventType
from codeframe.core.executor import Executor, ExecutionStatus, StepResult
from codeframe.core.fix_tracker import EscalationDecision, FixAttemptTracker, FixOutcome
from codeframe.core.gates import run as run_gates, GateResult, GateStatus
from codeframe.core.planner import ImplementationPlan, Planner, PlanStep, StepType
from codeframe.core.quick_fixes import apply_quick_fix, find_quick_fix
from codeframe.core.workspace import Workspace

if TYPE_CHECKING:
    from codeframe.core.conductor import GlobalFixCoordinator
    from codeframe.core.streaming import EventPublisher, RunOutputLogger

# Safe shell commands that can be executed without full shell interpretation
SAFE_SHELL_COMMANDS = frozenset({
    # Python tools
    "python", "python3", "pytest", "ruff", "black", "mypy", "pip", "uv",
    # Node tools
    "npm", "node", "npx", "yarn", "pnpm",
    # System tools
    "ls", "cat", "head", "tail", "grep", "find", "mkdir", "touch", "cp", "mv",
    # Git
    "git",
    # Testing
    "jest", "vitest", "cargo",
})


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


def _is_path_safe(file_path: Path, workspace_path: Path) -> tuple[bool, str]:
    """Check if a file path is safely within the workspace.

    Prevents path traversal attacks via '..' components.

    Args:
        file_path: The file path to check
        workspace_path: The workspace root path

    Returns:
        Tuple of (is_safe, reason) where reason explains any rejection
    """
    try:
        # Resolve both paths to handle symlinks and relative paths
        resolved_file = file_path.resolve()
        resolved_workspace = workspace_path.resolve()

        # Check if the file is within the workspace
        try:
            resolved_file.relative_to(resolved_workspace)
            return (True, "")
        except ValueError:
            return (False, f"Path escapes workspace: {file_path}")
    except Exception as e:
        return (False, f"Path resolution error: {e}")


def _parse_command_safely(command: str) -> tuple[list[str], bool, str]:
    """Parse a shell command into an argument list for safe execution.

    Args:
        command: The shell command string

    Returns:
        Tuple of (argv_list, requires_shell, warning) where:
        - argv_list: Parsed command arguments
        - requires_shell: True if command needs shell interpretation
        - warning: Non-empty if there are safety concerns
    """
    # Check for shell operators that require shell=True
    shell_operators = ['|', '&&', '||', '>', '<', '>>', '<<', ';', '$', '`', '$(']
    has_shell_operators = any(op in command for op in shell_operators)

    if has_shell_operators:
        return ([], True, "Command contains shell operators")

    try:
        # Parse command into argv list
        argv = shlex.split(command)
        if not argv:
            return ([], True, "Empty command")

        # Check if the base command is in our safe list
        base_cmd = Path(argv[0]).name  # Handle paths like /usr/bin/python
        if base_cmd not in SAFE_SHELL_COMMANDS:
            return (argv, True, f"Command '{base_cmd}' not in safe list")

        return (argv, False, "")
    except ValueError as e:
        # shlex.split failed (e.g., unclosed quotes)
        return ([], True, f"Command parse error: {e}")


class AgentStatus(str, Enum):
    """Current status of the agent."""

    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    BLOCKED = "blocked"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


class FixScope(str, Enum):
    """Scope of a proposed fix - determines coordination requirements.

    LOCAL: Agent can execute autonomously (files it created, its own tests)
    GLOBAL: Requires Conductor coordination (config files, installs, shared code)
    """

    LOCAL = "local"
    GLOBAL = "global"


# Files that require global coordination when modified
GLOBAL_SCOPE_FILES = {
    "pyproject.toml",
    "package.json",
    "tsconfig.json",
    "Cargo.toml",
    "go.mod",
    "requirements.txt",
    "setup.py",
    "setup.cfg",
    ".env",
    ".env.example",
    "Dockerfile",
    "docker-compose.yml",
    "Makefile",
}


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
MAX_CONSECUTIVE_VERIFICATION_FAILURES = 3

# TRUE requirements ambiguity - create blocker immediately
# These are situations where the agent genuinely cannot proceed without human input
REQUIREMENTS_AMBIGUITY_PATTERNS = [
    # True requirements conflicts
    "conflicting requirements",
    "spec unclear",
    "specification unclear",
    "requirements conflict",
    "contradictory requirements",
    # Business logic requiring domain knowledge
    "business decision",
    "business logic unclear",
    "domain knowledge required",
    "stakeholder decision",
    # Security policy ambiguity
    "security policy unclear",
    "compliance requirement unclear",
    "regulatory requirement",
]

# Access/credentials issues - always create blocker
# These truly require human intervention
ACCESS_PATTERNS = [
    "permission denied",
    "access denied",
    "authentication required",
    "api key",  # Covers "api key missing", "api key not configured", etc.
    "credentials",  # Covers "credentials missing", "credentials required", etc.
    "secret required",
    "token required",
    "unauthorized",
    "forbidden",
]

# External service issues - create blocker after retry
EXTERNAL_SERVICE_PATTERNS = [
    "service unavailable",
    "rate limited",
    "quota exceeded",
    "connection refused",
    "timeout exceeded",
]

# TACTICAL decisions - agent should resolve autonomously, NEVER block
# These patterns indicate the agent is asking about implementation details
# it should decide on its own using project preferences or best practices
TACTICAL_DECISION_PATTERNS = [
    # Implementation choices
    "which approach",
    "should i use",
    "multiple options",
    "design decision",
    "please clarify",
    "need clarification",
    # File handling
    "file already exists",
    "overwrite",
    "should i create",
    "should i delete",
    # Tooling choices
    "which version",
    "which package",
    "which framework",
    "install method",
    "package manager",
    # Configuration choices
    "which configuration",
    "which setting",
    "default value",
    "fixture scope",
    "loop scope",
    # Generic decision patterns
    "what do you",
    "do you want",
    "would you like",
    "prefer",
]

# Combined pattern for human input (requirements + access + external)
# NOTE: Tactical patterns are explicitly EXCLUDED - agent handles these autonomously
HUMAN_INPUT_PATTERNS = (
    REQUIREMENTS_AMBIGUITY_PATTERNS + ACCESS_PATTERNS + EXTERNAL_SERVICE_PATTERNS
)

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
        verbose: bool = False,
        fix_coordinator: Optional["GlobalFixCoordinator"] = None,
        output_logger: Optional["RunOutputLogger"] = None,
        event_publisher: Optional["EventPublisher"] = None,
    ):
        """Initialize the agent.

        Args:
            workspace: Target workspace
            llm_provider: LLM provider for planning and code generation
            max_context_tokens: Maximum tokens for context loading
            dry_run: If True, don't make actual changes
            on_event: Optional callback for agent events
            debug: If True, write detailed debug log to workspace
            verbose: If True, print detailed progress to stdout
            fix_coordinator: Optional coordinator for global fixes (for parallel execution)
            output_logger: Optional logger for streaming output to file (for cf work follow)
            event_publisher: Optional EventPublisher for SSE streaming (for web clients)
        """
        self.workspace = workspace
        self.llm = llm_provider
        self.max_context_tokens = max_context_tokens
        self.dry_run = dry_run
        self.on_event = on_event
        self.debug = debug
        self.verbose = verbose
        self.fix_coordinator = fix_coordinator
        self.output_logger = output_logger
        self.event_publisher = event_publisher

        self.state = AgentState()
        self.context: Optional[TaskContext] = None
        self.executor: Optional[Executor] = None

        # Fix attempt tracking for loop prevention and escalation
        self.fix_tracker = FixAttemptTracker()

        # Debug logging setup
        self._debug_log_path: Optional[Path] = None
        self._failure_count = 0  # Track failures for verbose logging
        if debug:
            self._setup_debug_log()

    def _verbose_print(self, message: str) -> None:
        """Print message to stdout (if verbose) and to output log file.

        The output log file is always written to (if logger provided) to enable
        streaming via `cf work follow`, even when verbose=False.

        Args:
            message: Message to print/log
        """
        # Print to stdout if verbose mode is enabled
        if self.verbose:
            print(message)

        # Always write to output log if logger is provided (for cf work follow)
        if self.output_logger:
            self.output_logger.write(message + "\n")

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
            event_publisher=self.event_publisher,
        )

        consecutive_failures = 0
        consecutive_verification_failures = 0

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
                            # Extract detailed error info from gate result
                            failed_checks = [
                                c for c in gate_result.checks
                                if c.status != GateStatus.PASSED
                            ]
                            failed_check_names = [c.name for c in failed_checks]

                            # Build detailed error string with actual output
                            error_details = []
                            for check in failed_checks:
                                if check.output:
                                    error_details.append(
                                        f"[{check.name}] {check.output[:500]}"
                                    )
                            error_detail_str = (
                                "\n".join(error_details)
                                if error_details
                                else "No details available"
                            )

                            self._emit_event("verification_failed", {
                                "step": step.index,
                                "error": f"Verification failed: {failed_check_names}",
                                "gates": failed_check_names,
                                "error_count": len(failed_checks),
                                "error_details": error_detail_str[:1000],
                            })

                            failed_result = StepResult(
                                step=step,
                                status=ExecutionStatus.FAILED,
                                error=(
                                    f"Verification failed: {failed_check_names}"
                                    f"\n{error_detail_str}"
                                ),
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

                            if self_correction_succeeded:
                                consecutive_verification_failures = 0
                            else:
                                # Couldn't fix the verification error
                                consecutive_verification_failures += 1
                                consecutive_failures += 1
                                if consecutive_verification_failures >= MAX_CONSECUTIVE_VERIFICATION_FAILURES:
                                    self._debug_log(
                                        f"ABORTING: Too many consecutive verification failures ({consecutive_verification_failures})",
                                        level="ERROR",
                                        always=True,
                                    )
                                    self._emit_event("execution_aborted", {
                                        "reason": f"Too many consecutive verification failures ({consecutive_verification_failures})",
                                        "step": step.index,
                                    })
                                    self._create_blocker_from_failure(step, current_result)
                                    return
                                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                                    self._create_blocker_from_failure(step, current_result)
                                    return
                                # Otherwise, continue to next step with broken file

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
                verbose=True,
            )
            self.state.gate_results.append(result)
            return result
        except Exception:
            return None

    def _run_final_verification(self) -> None:
        """Run full verification gates with self-correction loop.

        This method implements a retry loop that:
        1. Runs verification gates (pytest, ruff)
        2. If gates pass, marks task as COMPLETED
        3. If gates fail, attempts self-correction:
           a. Try ruff --fix for lint issues
           b. Use LLM to generate fix plan for remaining errors
           c. Execute fix steps
           d. Re-run verification
        4. Repeats until max_attempts or gives up
        """
        self.state.status = AgentStatus.VERIFYING
        self._emit_event("verification_started", {})

        print(f"\n[VERIFY] Starting final verification (max {self.state.max_attempts} attempts)")
        self._debug_log(
            f"Starting final verification (max {self.state.max_attempts} attempts)",
            level="INFO",
            always=True,
        )

        while self.state.attempt_count < self.state.max_attempts:
            attempt_num = self.state.attempt_count + 1
            self._verbose_print(f"[VERIFY] Attempt {attempt_num}/{self.state.max_attempts}")
            self._debug_log(
                f"Verification attempt {attempt_num}/{self.state.max_attempts}",
                level="INFO",
            )

            try:
                result = run_gates(self.workspace, verbose=False)
                self.state.gate_results.append(result)

                if result.passed:
                    self.state.status = AgentStatus.COMPLETED
                    self._emit_event("verification_passed", {"attempt": attempt_num})
                    self._verbose_print(f"[VERIFY] PASSED on attempt {attempt_num}")
                    self._debug_log(
                        f"Verification PASSED on attempt {attempt_num}",
                        level="INFO",
                        always=True,
                    )
                    return  # Success!

                # Verification failed - log details
                failed_checks = [
                    c.name for c in result.checks
                    if c.status == GateStatus.FAILED
                ]
                self._verbose_print(f"[VERIFY] FAILED: {', '.join(failed_checks)}")
                self._debug_log(
                    f"Verification failed: {', '.join(failed_checks)}",
                    level="WARN",
                    always=True,
                )

                # Increment attempt count
                self.state.attempt_count += 1

                # Check if we have retries left
                if self.state.attempt_count >= self.state.max_attempts:
                    self._debug_log(
                        f"Max attempts ({self.state.max_attempts}) exceeded",
                        level="ERROR",
                        always=True,
                    )
                    break  # Exit loop, fall through to FAILED

                # Attempt self-correction
                self._verbose_print("[VERIFY] Attempting self-correction...")
                self._emit_event("self_correction_started", {
                    "attempt": attempt_num,
                    "failed_checks": failed_checks,
                })

                fixed = self._attempt_verification_fix(result)
                if not fixed:
                    self._verbose_print("[VERIFY] Self-correction FAILED, giving up")
                    self._debug_log(
                        "Self-correction failed, giving up",
                        level="ERROR",
                        always=True,
                    )
                    break  # Can't fix, fall through to FAILED

                self._verbose_print("[VERIFY] Self-correction applied, re-running verification...")
                self._debug_log(
                    "Self-correction applied, re-running verification",
                    level="INFO",
                    always=True,
                )
                # Loop back to re-run gates

            except Exception as e:
                self._verbose_print(f"[VERIFY] Exception: {e}")
                self._emit_event("verification_error", {"error": str(e)})
                self._debug_log(
                    f"Verification error: {e}",
                    level="ERROR",
                    always=True,
                )
                break  # Exit on exception

        # Max attempts exceeded or couldn't fix
        self._verbose_print(f"[VERIFY] Final result: FAILED after {self.state.attempt_count} attempts")
        self.state.status = AgentStatus.FAILED
        self._emit_event("verification_failed", {
            "reason": "Max verification attempts exceeded or self-correction failed",
            "attempts": self.state.attempt_count,
        })

    def _try_auto_fix(self, gate_result: GateResult) -> bool:
        """Try to automatically fix lint issues.

        Returns:
            True if auto-fix was successful (returncode == 0)
        """
        if not self.executor or self.dry_run:
            return False

        import subprocess

        try:
            result = subprocess.run(
                ["ruff", "check", "--fix", "."],
                cwd=self.workspace.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                self._debug_log("ruff --fix succeeded", level="INFO")
                return True
            else:
                # Ruff fix failed - log the error output
                stderr_preview = result.stderr[:500] if result.stderr else ""
                stdout_preview = result.stdout[:500] if result.stdout else ""
                self._debug_log(
                    f"ruff --fix failed (exit {result.returncode}): {stderr_preview or stdout_preview}",
                    level="WARN",
                )
                return False

        except subprocess.TimeoutExpired:
            self._debug_log("ruff --fix timed out after 30s", level="WARN")
            return False
        except subprocess.CalledProcessError as e:
            self._debug_log(f"ruff --fix raised CalledProcessError: {e}", level="WARN")
            return False
        except FileNotFoundError:
            self._debug_log("ruff command not found", level="WARN")
            return False
        except Exception as e:
            self._debug_log(f"ruff --fix error: {e}", level="WARN")
            return False

    def _build_self_correction_context(self) -> str:
        """Build rich context for intelligent self-correction.

        Provides the LLM with project structure, config files, and file tree
        so it can reason about local vs external packages, project layout, etc.

        Returns:
            Formatted context string for the self-correction prompt
        """
        sections = []

        # Project structure overview
        sections.append("## Project Structure")
        if self.context and self.context.file_tree:
            # Group files by directory
            dirs: dict[str, list[str]] = {}
            for f in self.context.file_tree[:50]:  # Limit to 50 files
                from pathlib import Path as P
                dir_path = str(P(f.path).parent)
                if dir_path not in dirs:
                    dirs[dir_path] = []
                dirs[dir_path].append(P(f.path).name)

            for dir_path in sorted(dirs.keys())[:15]:
                sections.append(f"  {dir_path}/")
                for filename in dirs[dir_path][:8]:
                    sections.append(f"    {filename}")
                if len(dirs[dir_path]) > 8:
                    sections.append(f"    ... ({len(dirs[dir_path]) - 8} more)")
        sections.append("")

        # Key config files content
        config_files = ["pyproject.toml", "package.json", "Cargo.toml", "go.mod", "setup.py"]
        for config_name in config_files:
            config_path = self.workspace.repo_path / config_name
            if config_path.exists():
                try:
                    content = config_path.read_text()[:2000]  # Limit size
                    sections.append(f"## {config_name}")
                    sections.append("```")
                    sections.append(content)
                    sections.append("```")
                    sections.append("")
                except Exception:
                    pass

        # Tech stack info if available
        if self.context and self.context.tech_stack:
            sections.append("## Tech Stack")
            sections.append(self.context.tech_stack)
            sections.append("")

        # Files this agent created/modified in this run
        if self.state.step_results:
            modified_files = set()
            for result in self.state.step_results:
                for change in result.file_changes:
                    modified_files.add(str(change.path))
            if modified_files:
                sections.append("## Files Modified by This Task")
                for f in sorted(modified_files)[:20]:
                    sections.append(f"  - {f}")
                sections.append("")

        return "\n".join(sections)

    def _classify_fix_scope(self, fix: dict) -> FixScope:
        """Classify whether a fix is local or global.

        Args:
            fix: Fix dictionary with 'file', 'action', 'command' keys

        Returns:
            FixScope.LOCAL or FixScope.GLOBAL
        """
        action = fix.get("action", "")
        file_path = fix.get("file", "")
        command = fix.get("command", "")

        # Shell commands that modify project state are global
        if action == "shell":
            global_commands = ["pip install", "npm install", "uv add", "cargo add",
                               "go get", "yarn add", "pnpm add", "poetry add"]
            for gc in global_commands:
                if gc in command:
                    return FixScope.GLOBAL

        # Creating new directories at project root is global
        if action == "create_directory":
            # Root-level or src/ directories are global
            if "/" not in file_path or file_path.startswith("src/"):
                return FixScope.GLOBAL

        # Modifying config files is always global
        from pathlib import Path as P
        filename = P(file_path).name if file_path else ""
        if filename in GLOBAL_SCOPE_FILES:
            return FixScope.GLOBAL

        # Check if file was created by this agent in this run
        if self.state.step_results:
            files_this_run = set()
            for result in self.state.step_results:
                for change in result.file_changes:
                    files_this_run.add(str(change.path))
            if file_path in files_this_run:
                return FixScope.LOCAL

        # Default to global for safety
        return FixScope.GLOBAL

    def _attempt_verification_fix(self, gate_result: GateResult) -> bool:
        """Attempt to self-correct verification failures.

        Strategy:
        1. Try ruff --fix for quick lint fixes
        2. Try pattern-based quick fixes (no LLM needed)
        3. Collect error messages from failed checks
        4. Check if we should escalate to blocker
        5. Use LLM to generate a fix plan
        6. Execute the fix plan steps
        7. Return True if fixes were applied (caller will re-verify)

        Args:
            gate_result: Result of failed verification gates

        Returns:
            True if fixes were applied, False if unable to fix
        """
        self._verbose_print("[SELFCORRECT] Starting verification fix attempt")
        self._debug_log("Attempting self-correction", level="INFO", always=True)

        # Step 1: Try ruff --fix for quick lint fixes
        self._verbose_print("[SELFCORRECT] Running ruff --fix...")
        self._try_auto_fix(gate_result)

        # Step 2: Collect error messages from failed checks
        errors = []
        for check in gate_result.checks:
            if check.status == GateStatus.FAILED and check.output:
                errors.append(f"{check.name}: {check.output[:1000]}")

        if not errors:
            self._verbose_print("[SELFCORRECT] No error messages to fix")
            self._debug_log("No error messages to fix", level="WARN")
            return False

        self._verbose_print(f"[SELFCORRECT] Collected {len(errors)} error(s) to fix")
        error_summary = "\n\n".join(errors)
        self._debug_log(f"Errors to fix:\n{error_summary[:500]}...", level="INFO")

        # Step 3: Try pattern-based quick fixes first (no LLM needed)
        quick_fix_applied = False
        for error in errors:
            quick_fix = find_quick_fix(
                error,
                repo_path=self.workspace.repo_path,
            )
            if quick_fix:
                # Check if we already tried this fix
                if self.fix_tracker.was_attempted(error, quick_fix.description):
                    self._verbose_print(f"[SELFCORRECT] Skipping already-tried fix: {quick_fix.description}")
                    self._debug_log(f"Skipping duplicate fix: {quick_fix.description}", level="INFO")
                    continue

                # Record the attempt
                self.fix_tracker.record_attempt(error, quick_fix.description)

                self._verbose_print(f"[SELFCORRECT] Trying quick fix: {quick_fix.description}")
                success, msg = apply_quick_fix(quick_fix, self.workspace.repo_path, self.dry_run)

                if success:
                    self.fix_tracker.record_outcome(error, quick_fix.description, FixOutcome.SUCCESS)
                    self._verbose_print(f"[SELFCORRECT] Quick fix applied: {msg}")
                    self._debug_log(f"Quick fix applied: {msg}", level="INFO", always=True)
                    quick_fix_applied = True
                else:
                    self.fix_tracker.record_outcome(error, quick_fix.description, FixOutcome.FAILED)
                    self._verbose_print(f"[SELFCORRECT] Quick fix failed: {msg}")
                    self._debug_log(f"Quick fix failed: {msg}", level="WARN")

        if quick_fix_applied:
            return True  # Let caller re-verify

        # Step 4: Check if we should escalate to blocker
        escalation = self.fix_tracker.should_escalate(error_summary)
        if escalation.should_escalate:
            self._verbose_print(f"[SELFCORRECT] Escalating to blocker: {escalation.reason}")
            self._debug_log(f"Escalating to blocker: {escalation.reason}", level="WARN", always=True)
            self._create_escalation_blocker(error_summary, escalation)
            return False  # Stop trying, blocker created

        # Step 5: Use LLM to generate a fix plan with full context
        # Build rich context so LLM can reason about project structure
        project_context = self._build_self_correction_context()

        # Include info about already-tried fixes to avoid repetition
        attempted_fixes = self.fix_tracker.get_attempted_fixes(error_summary)
        already_tried = ""
        if attempted_fixes:
            already_tried = "\n\nALREADY TRIED (DO NOT REPEAT):\n" + "\n".join(f"- {f}" for f in attempted_fixes)

        fix_prompt = f"""You are an intelligent agent fixing verification errors. You have access to the full project context below.

{project_context}

## Errors to Fix

{error_summary}

## Instructions

Analyze the errors and the project structure. Determine the root cause and propose fixes.

You can use ANY of these actions:
- "edit": Modify existing file (requires old_code, new_code)
- "create": Create new file (requires content)
- "shell": Run a shell command (requires command)

Return a JSON object:
{{
    "analysis": "What's the root cause? Is this a local code issue or a project configuration issue?",
    "fixes": [
        {{
            "action": "edit|create|shell",
            "scope": "local|global",
            "description": "What this fix does",
            "file": "path/to/file.py",
            "old_code": "for edits only",
            "new_code": "for edits only",
            "content": "for creates only",
            "command": "for shell only"
        }}
    ]
}}

## Scope Classification (IMPORTANT for parallel execution)
- "local": Fixes to files YOU created in this task, your own tests, formatting fixes
- "global": Config files (pyproject.toml, package.json), install commands, new packages, shared code

## Common Patterns
- ModuleNotFoundError for LOCAL package (src/foo exists): Use "uv pip install -e ." or fix pyproject.toml
- ModuleNotFoundError for EXTERNAL package: Use "uv pip install <package>"
- Import errors in your code: Edit the file to fix imports
- Syntax errors: Edit the file to fix syntax

IMPORTANT:
- Check if the module exists locally before trying to install it
- Be precise with old_code - it must match exactly
- Return valid JSON only{already_tried}"""

        try:
            self._verbose_print("[SELFCORRECT] Asking LLM for fixes...")
            response = self.llm.complete(
                messages=[{"role": "user", "content": fix_prompt}],
                purpose=Purpose.EXECUTION,
                system="You are a code fixer. Return only valid JSON.",
                max_tokens=4096,
                temperature=0.0,
            )

            # Parse the fix plan
            import json
            json_match = re.search(r"\{[\s\S]*\}", response.content)
            if not json_match:
                self._verbose_print("[SELFCORRECT] No JSON found in LLM response")
                self._debug_log("No JSON found in fix response", level="ERROR")
                return False

            fix_plan = json.loads(json_match.group())
            fixes = fix_plan.get("fixes", [])

            if not fixes:
                self._verbose_print("[SELFCORRECT] LLM returned empty fixes list")
                self._debug_log("No fixes generated", level="WARN")
                return False

            analysis = fix_plan.get('analysis', 'no analysis')
            self._verbose_print(f"[SELFCORRECT] LLM generated {len(fixes)} fix(es): {analysis[:100]}...")
            self._debug_log(
                f"Generated {len(fixes)} fixes: {analysis}",
                level="INFO",
                always=True,
            )

            # Step 6: Execute the fix plan with tracking
            applied = 0
            for fix in fixes:
                file_path = self.workspace.repo_path / fix.get("file", "")
                action = fix.get("action", "edit")
                fix_desc = fix.get("description", f"{action} {fix.get('file', 'unknown')}")

                # Track the attempt
                self.fix_tracker.record_attempt(
                    error_summary, fix_desc, file_path=str(file_path)
                )

                try:
                    fix_succeeded = False

                    if action == "create":
                        # Create new file with path safety check
                        content = fix.get("content", "")
                        if content and not self.dry_run:
                            # Verify path is safely within workspace
                            is_safe, reason = _is_path_safe(file_path, self.workspace.repo_path)
                            if not is_safe:
                                self._debug_log(f"Create blocked: {reason}", level="WARN")
                            else:
                                file_path.parent.mkdir(parents=True, exist_ok=True)
                                file_path.write_text(content)
                                self._debug_log(f"Created {file_path}", level="INFO")
                                applied += 1
                                fix_succeeded = True

                    elif action == "edit":
                        # Edit existing file with path safety check
                        old_code = fix.get("old_code", "")
                        new_code = fix.get("new_code", "")

                        # Verify path is safely within workspace before any file ops
                        is_safe, reason = _is_path_safe(file_path, self.workspace.repo_path)
                        if not is_safe:
                            self._debug_log(f"Edit blocked: {reason}", level="WARN")
                        elif not file_path.exists():
                            self._debug_log(f"File not found: {file_path}", level="WARN")
                        elif not old_code:
                            self._debug_log(f"No old_code for {file_path}", level="WARN")
                        else:
                            content = file_path.read_text()
                            if old_code not in content:
                                self._debug_log(
                                    f"old_code not found in {file_path}",
                                    level="WARN",
                                )
                            elif not self.dry_run:
                                new_content = content.replace(old_code, new_code, 1)
                                file_path.write_text(new_content)
                                self._debug_log(f"Fixed {file_path}", level="INFO")
                                applied += 1
                                fix_succeeded = True

                    elif action == "delete":
                        # Delete file with safeguards
                        if self.dry_run:
                            self._debug_log(f"[DRY RUN] Would delete {file_path}", level="INFO")
                        elif not file_path.exists():
                            self._debug_log(f"File already deleted: {file_path}", level="INFO")
                            fix_succeeded = True
                        else:
                            # Verify path is safely within workspace
                            is_safe, reason = _is_path_safe(file_path, self.workspace.repo_path)
                            if not is_safe:
                                self._debug_log(f"Delete blocked: {reason}", level="WARN")
                            else:
                                file_path.unlink()
                                self._debug_log(f"Deleted {file_path}", level="INFO")
                                applied += 1
                                fix_succeeded = True

                    elif action == "shell":
                        # Run shell command with safe parsing
                        command = fix.get("command", "")
                        if command and not self.dry_run:
                            scope = self._classify_fix_scope(fix)
                            self._verbose_print(f"[SELFCORRECT] Running shell ({scope.value}): {command[:80]}...")

                            # Parse command for safe execution
                            argv, requires_shell, parse_warning = _parse_command_safely(command)

                            # Reject commands that require shell=True (contain operators/unsafe constructs)
                            if requires_shell:
                                self._debug_log(
                                    f"Shell command rejected: {parse_warning} - command: {command[:100]}",
                                    level="ERROR",
                                )
                                self._verbose_print(
                                    f"[SELFCORRECT] Command rejected (requires shell): {parse_warning}"
                                )
                                # Mark as failed and skip execution
                                self.fix_tracker.record_outcome(
                                    error_summary, fix_desc, FixOutcome.FAILED
                                )
                                continue  # Skip to next fix

                            if parse_warning:
                                self._debug_log(f"Shell safety: {parse_warning}", level="WARN")

                            # Helper to run the command safely (only shell=False now)
                            def _run_command() -> subprocess.CompletedProcess:
                                return subprocess.run(
                                    argv,
                                    shell=False,
                                    cwd=self.workspace.repo_path,
                                    capture_output=True,
                                    text=True,
                                    timeout=120,
                                )

                            # Global scope commands should go through Coordinator
                            if scope == FixScope.GLOBAL and self.fix_coordinator:
                                status, should_execute = self.fix_coordinator.request_fix(
                                    error=error_summary,
                                    fix_type="shell",
                                    fix_description=fix_desc,
                                    command=command,
                                    task_id=self.state.task_id,
                                )
                                if status == "already_completed":
                                    # Another agent already fixed this
                                    self._verbose_print("[SELFCORRECT] Fix already done by another agent")
                                    applied += 1
                                    fix_succeeded = True
                                elif status == "pending":
                                    # Wait for another agent to finish
                                    self._verbose_print("[SELFCORRECT] Waiting for another agent's fix...")
                                    if self.fix_coordinator.wait_for_fix(error_summary, timeout=60.0):
                                        applied += 1
                                        fix_succeeded = True
                                    else:
                                        self._debug_log("Timeout waiting for global fix", level="WARN")
                                elif should_execute:
                                    # We are responsible for executing
                                    try:
                                        result = _run_command()
                                        success = result.returncode == 0
                                        self.fix_coordinator.report_fix_result(
                                            error_summary, success, result.stderr[:200] if not success else None
                                        )
                                        if success:
                                            self._debug_log(f"Global shell command succeeded: {command}", level="INFO")
                                            applied += 1
                                            fix_succeeded = True
                                        else:
                                            self._debug_log(f"Global shell command failed: {result.stderr[:200]}", level="WARN")
                                    except Exception as shell_err:
                                        self.fix_coordinator.report_fix_result(error_summary, False, str(shell_err))
                                        self._debug_log(f"Global shell error: {shell_err}", level="WARN")
                            else:
                                # Local scope - execute directly
                                try:
                                    result = _run_command()
                                    if result.returncode == 0:
                                        self._debug_log(f"Shell command succeeded: {command}", level="INFO")
                                        applied += 1
                                        fix_succeeded = True
                                    else:
                                        self._debug_log(
                                            f"Shell command failed: {result.stderr[:200]}",
                                            level="WARN"
                                        )
                                except subprocess.TimeoutExpired:
                                    self._debug_log(f"Shell command timed out: {command}", level="WARN")
                                except Exception as shell_err:
                                    self._debug_log(f"Shell command error: {shell_err}", level="WARN")

                    # Record outcome
                    self.fix_tracker.record_outcome(
                        error_summary, fix_desc,
                        FixOutcome.SUCCESS if fix_succeeded else FixOutcome.FAILED
                    )

                except Exception as e:
                    self._debug_log(f"Fix failed for {file_path}: {e}", level="ERROR")
                    self.fix_tracker.record_outcome(error_summary, fix_desc, FixOutcome.FAILED)

            self._verbose_print(f"[SELFCORRECT] Applied {applied}/{len(fixes)} fixes")
            self._debug_log(
                f"Applied {applied}/{len(fixes)} fixes",
                level="INFO",
                always=True,
            )
            return applied > 0

        except json.JSONDecodeError as e:
            self._verbose_print(f"[SELFCORRECT] JSON parse error: {e}")
            self._debug_log(f"Failed to parse fix plan JSON: {e}", level="ERROR")
            return False
        except Exception as e:
            self._verbose_print(f"[SELFCORRECT] Error: {e}")
            self._debug_log(f"Self-correction error: {e}", level="ERROR")
            return False

    def _classify_error(self, error: str) -> str:
        """Classify an error as technical, tactical, or human-input-needed.

        Error classification hierarchy:
        1. TACTICAL - Agent asking about implementation details it should decide itself
        2. HUMAN - True requirements ambiguity or access issues
        3. TECHNICAL - Coding errors the agent can self-correct

        Args:
            error: Error message to classify

        Returns:
            "tactical" if agent should decide autonomously (no blocker)
            "technical" if agent can self-correct
            "human" if genuinely needs human input (create blocker)
        """
        error_lower = error.lower()

        # Check tactical patterns FIRST - these should NEVER create blockers
        # Agent should resolve these using preferences or best judgment
        for pattern in TACTICAL_DECISION_PATTERNS:
            if pattern in error_lower:
                return "tactical"

        # Check true human-input patterns (requirements ambiguity + access issues)
        for pattern in HUMAN_INPUT_PATTERNS:
            if pattern in error_lower:
                return "human"

        # Check technical patterns
        for pattern in TECHNICAL_ERROR_PATTERNS:
            if pattern in error_lower:
                return "technical"

        # Default to technical - agent should try to fix it first
        return "technical"

    def _resolve_tactical_decision(self, error: str, context: "TaskContext") -> str:
        """Resolve a tactical decision using preferences and best judgment.

        When the agent encounters a tactical question (implementation detail,
        tooling choice, file handling, etc.), this method resolves it
        autonomously instead of creating a blocker.

        Args:
            error: The error/question that triggered this
            context: Task context with preferences

        Returns:
            Resolution instruction for the agent to follow
        """
        self._emit_event("tactical_resolution_started", {"question": error[:200]})

        # Build resolution prompt using preferences
        prefs = context.preferences
        pref_section = prefs.to_prompt_section() if prefs.has_preferences() else ""

        prompt = f"""You encountered a tactical implementation decision that should be resolved autonomously.

## The Question/Decision
{error}

{pref_section}

## Resolution Guidelines

As an expert software engineer, resolve this decision using:
1. Project preferences (above) if they apply
2. Industry best practices if no preference
3. The simpler approach when multiple options are equivalent
4. Common conventions for this type of project

IMPORTANT: This is a tactical decision you MUST resolve yourself. Do NOT ask the user.
Do NOT say you need clarification. Make the best decision and proceed.

Respond with a brief, clear instruction on what to do. For example:
- "Use pytest as the test framework"
- "Overwrite the existing file with the new implementation"
- "Use the latest stable version of the library"
- "Install using uv (the project's package manager)"

Your decision:"""

        try:
            response = self.llm.complete(
                messages=[{"role": "user", "content": prompt}],
                purpose=Purpose.GENERATION,
                max_tokens=256,
                temperature=0.0,
            )

            resolution = response.strip()
            self._emit_event(
                "tactical_resolution_completed",
                {"question": error[:200], "resolution": resolution[:200]},
            )
            self._debug_log(
                f"TACTICAL DECISION RESOLVED: {resolution[:100]}",
                level="INFO",
                data={"question": error, "resolution": resolution},
            )
            return resolution

        except Exception as e:
            # On LLM failure, use a sensible default
            self._emit_event(
                "tactical_resolution_failed", {"question": error[:200], "error": str(e)}
            )
            return "Proceed with the most common/standard approach for this situation."

    def _should_create_blocker(
        self,
        consecutive_failures: int,
        result: StepResult,
        self_correction_attempts: int = 0,
    ) -> bool:
        """Determine if we should create a blocker.

        Blockers are only created for genuine human-input-needed situations.
        Technical errors should be handled by self-correction first.
        Tactical decisions should NEVER create blockers - agent resolves them.

        Args:
            consecutive_failures: Number of consecutive step failures
            result: The failed step result
            self_correction_attempts: How many self-correction attempts were made

        Returns:
            True if a blocker should be created
        """
        error_type = self._classify_error(result.error)

        # TACTICAL decisions NEVER create blockers
        # The agent should resolve these autonomously using preferences
        if error_type == "tactical":
            self._debug_log(
                "TACTICAL decision detected - will resolve autonomously, NOT creating blocker",
                level="INFO",
                data={"error": result.error[:200]},
            )
            return False

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
        """Create a blocker from a step failure.

        May resolve autonomously if the LLM determines the issue is tactical.
        Only creates actual blockers for issues requiring human input.
        """
        question = self._generate_blocker_question(step, result)

        # Check if LLM determined this should be resolved autonomously
        if question.startswith("RESOLVE_AUTONOMOUSLY:"):
            self._debug_log(
                f"Auto-resolving tactical decision: {question}",
                level="INFO",
                always=True,
            )
            # Don't create a blocker - let the agent continue with self-correction
            self._emit_event("tactical_resolved", {
                "step": step.index,
                "resolution": question,
            })
            return

        # Check if LLM determined this is a technical fix
        if question.startswith("TECHNICAL_FIX:"):
            self._debug_log(
                f"Technical issue identified: {question}",
                level="INFO",
                always=True,
            )
            # Don't create a blocker - mark as needing retry
            self._emit_event("technical_fix_needed", {
                "step": step.index,
                "fix": question,
            })
            return

        # Also check for tactical patterns in the question itself
        question_lower = question.lower()
        tactical_indicators = [
            "virtual environment", "venv", "virtualenv",
            "would you like me to", "would you prefer",
            "should i create", "should i use",
            "pip install", "npm install", "uv sync",
            "break-system-packages", "pipx",
            "pytest.ini", "pyproject.toml", "asyncio_default_fixture_loop_scope",
            "fixture scope", "loop scope",
        ]

        if any(indicator in question_lower for indicator in tactical_indicators):
            self._debug_log(
                f"Detected tactical question pattern, auto-resolving: {question[:100]}...",
                level="INFO",
                always=True,
            )
            self._emit_event("tactical_resolved", {
                "step": step.index,
                "resolution": "Auto-resolved tactical decision",
            })
            return

        # This is a legitimate blocker that requires human input
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
        """Handle verification failure.

        Verification failures (pytest, ruff, etc.) are TECHNICAL issues,
        not human decision points. We mark the task as FAILED instead of
        BLOCKED so the retry mechanism can handle it.

        This prevents tactical questions like "pytest failed, what should I do?"
        from becoming blockers that require human intervention.
        """
        failed_checks = [
            c.name for c in gate_result.checks
            if c.status == GateStatus.FAILED
        ]

        self._debug_log(
            f"Verification failed for: {', '.join(failed_checks)}. "
            "Marking as FAILED (not BLOCKED) for retry.",
            level="WARN",
            always=True,
        )

        # Mark as FAILED, not BLOCKED - verification failures are technical
        # issues that should be retried, not human decision points
        self.state.status = AgentStatus.FAILED
        self._emit_event("verification_failed", {
            "failed_checks": failed_checks,
            "reason": "Verification failed - technical issue for retry",
        })
        # Note: task status update handled by runtime.fail_run()

    def _create_escalation_blocker(
        self,
        error_summary: str,
        escalation: EscalationDecision,
    ) -> None:
        """Create a blocker when self-correction has been exhausted.

        Unlike regular blockers which ask for guidance, escalation blockers
        provide detailed context about what was tried and why we're stuck.

        Args:
            error_summary: Summary of the errors being fixed
            escalation: EscalationDecision from FixAttemptTracker
        """

        # Build a detailed, informative question
        context = self.fix_tracker.get_blocker_context(error_summary)

        # Format attempted fixes
        fixes_list = ""
        if escalation.attempted_fixes:
            fixes_list = "\n".join(f"  - {f}" for f in escalation.attempted_fixes[:10])

        question = f"""Task failed after multiple self-correction attempts.

**Error:** {context.get('error_type', 'Unknown error')}

**Problem:** {escalation.error_summary[:300]}

**Attempted fixes ({context.get('attempt_count', 0)} total):**
{fixes_list}

**Reason for escalation:** {escalation.reason}

**How should I proceed?** Please provide guidance on:
1. What might be causing this persistent error?
2. Is there a different approach I should try?
3. Are there any missing dependencies or configuration?"""

        # Create the blocker
        blocker = blockers.create(
            workspace=self.workspace,
            question=question,
            task_id=self.state.task_id,
        )

        self.state.status = AgentStatus.BLOCKED
        self.state.blocker = BlockerInfo(
            reason=escalation.reason,
            question=question,
            context=f"Self-correction exhausted after {context.get('attempt_count', 0)} attempts",
        )

        self._emit_event("escalation_blocker_created", {
            "blocker_id": blocker.id,
            "reason": escalation.reason,
            "attempt_count": context.get("attempt_count", 0),
            "attempted_fixes": escalation.attempted_fixes,
        })

        self._debug_log(
            f"Created escalation blocker: {blocker.id}",
            level="INFO",
            data={
                "reason": escalation.reason,
                "attempt_count": context.get("attempt_count", 0),
            },
            always=True,
        )

    def _generate_blocker_question(
        self,
        step: PlanStep,
        result: StepResult,
    ) -> str:
        """Generate a helpful question for the blocker.

        Only generates questions for issues that truly require human input.
        Tactical decisions are auto-resolved, not turned into blockers.
        """
        # Use LLM to generate a clear question
        prompt = f"""A code execution step failed. Generate a clear, specific question to ask the user for help.

Step: {step.description}
Target: {step.target}
Error: {result.error}

CRITICAL INSTRUCTIONS:
1. ONLY generate a question if human input is TRULY required
2. Do NOT ask about tactical decisions - these should be resolved autonomously:
   - Virtual environments (always create one)
   - Package managers (use uv/pip/npm as appropriate)
   - Test frameworks (use pytest/jest)
   - File handling (overwrite existing files)
   - Configuration options (use sensible defaults)
   - Asyncio fixture scopes (use function scope)

3. DO ask about:
   - Conflicting requirements in the specification
   - Missing API keys or credentials
   - Business logic that requires domain expertise
   - Security policy clarifications

4. If the error is a tactical decision, respond with: "RESOLVE_AUTONOMOUSLY: [your decision]"
   For example: "RESOLVE_AUTONOMOUSLY: Create virtual environment and install dependencies"

5. If the error is a technical issue (syntax error, import error, test failure), respond with:
   "TECHNICAL_FIX: [what to fix]"

Generate a single question OR a RESOLVE_AUTONOMOUSLY/TECHNICAL_FIX directive:"""

        try:
            response = self.llm.complete(
                messages=[{"role": "user", "content": prompt}],
                purpose=Purpose.GENERATION,
                max_tokens=300,
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

        # Publish to SSE EventPublisher for web clients
        if self.event_publisher and self.state.task_id:
            try:
                self._publish_sse_event(event_type, data)
            except Exception:
                pass  # Don't fail on SSE emission

    def _publish_sse_event(self, event_type: str, data: dict) -> None:
        """Publish an event to SSE subscribers.

        Maps internal agent events to SSE ExecutionEvent types.

        Args:
            event_type: Internal event type (step_started, step_completed, etc.)
            data: Event data
        """
        from codeframe.core.models import ProgressEvent, OutputEvent, ErrorEvent, CompletionEvent

        task_id = self.state.task_id

        # Map internal events to SSE events
        if event_type == "step_started":
            total_steps = len(self.state.plan.steps) if self.state.plan else 1
            event = ProgressEvent(
                task_id=task_id,
                phase="execution",
                step=data.get("step", 0),
                total_steps=total_steps,
                message=f"Step {data.get('step', 0)}: {data.get('target', 'unknown')}",
            )
            self.event_publisher.publish_sync(task_id, event)

        elif event_type == "step_completed":
            output = data.get("output", "")
            if output:
                event = OutputEvent(
                    task_id=task_id,
                    stream="stdout",
                    line=output[:500],
                )
                self.event_publisher.publish_sync(task_id, event)

        elif event_type == "step_failed":
            event = ErrorEvent(
                task_id=task_id,
                error_type="step_failed",
                error=data.get("error", "Step failed"),
            )
            self.event_publisher.publish_sync(task_id, event)

        elif event_type == "verification_failed":
            event = ErrorEvent(
                task_id=task_id,
                error_type="verification_failed",
                error=data.get("error", "Verification failed"),
            )
            self.event_publisher.publish_sync(task_id, event)

        elif event_type in ("agent_completed", "agent_finished"):
            # Handle both "agent_completed" and "agent_finished" (run() emits "agent_finished")
            status = data.get("status", "completed")
            # Map AgentStatus values to SSE completion status
            if status in ("completed", "COMPLETED"):
                sse_status = "completed"
            elif status in ("failed", "FAILED"):
                sse_status = "failed"
            elif status in ("blocked", "BLOCKED"):
                sse_status = "blocked"
            else:
                sse_status = status

            event = CompletionEvent(
                task_id=task_id,
                status=sse_status,
                duration_seconds=0,  # Could track this
                files_modified=[c.path for c in (self.executor.changes if self.executor else [])],
            )
            self.event_publisher.publish_sync(task_id, event)
            self.event_publisher.complete_task_sync(task_id)

        elif event_type == "agent_failed":
            event = ErrorEvent(
                task_id=task_id,
                error_type="agent_failed",
                error=data.get("error", "Agent execution failed"),
            )
            self.event_publisher.publish_sync(task_id, event)
            self.event_publisher.complete_task_sync(task_id)

        elif event_type == "blocker_created":
            from codeframe.core.models import BlockerEvent
            event = BlockerEvent(
                task_id=task_id,
                blocker_id=data.get("blocker_id", ""),
                question=data.get("question", ""),
                context=data.get("context", ""),
            )
            self.event_publisher.publish_sync(task_id, event)

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
