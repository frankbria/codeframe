"""ReAct-style agent for CodeFRAME v3.

Implements a tool-use loop where the LLM reasons, acts (via tools),
and observes results iteratively until the task is complete.

This module is headless - no FastAPI or HTTP dependencies.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable, Optional

from codeframe.adapters.llm.base import LLMProvider, Purpose, ToolResult
from codeframe.core import blockers, events, gates
from codeframe.core.agent import AgentStatus
from codeframe.core.blocker_detection import classify_error_for_blocker
from codeframe.core.context import ContextLoader, TaskContext
from codeframe.core.events import EventType
from codeframe.core.fix_tracker import EscalationDecision, FixAttemptTracker, FixOutcome
from codeframe.core.models import AgentPhase, CompletionEvent, ErrorEvent, ProgressEvent
from codeframe.core.quick_fixes import apply_quick_fix, find_quick_fix
from codeframe.core.tools import AGENT_TOOLS, execute_tool
from codeframe.core.workspace import Workspace

if TYPE_CHECKING:
    from codeframe.core.conductor import GlobalFixCoordinator
    from codeframe.core.streaming import EventPublisher, RunOutputLogger

logger = logging.getLogger(__name__)

# Rough token budget for conversation history to avoid overflowing LLM context.
_MAX_HISTORY_CHARS = 400_000  # ~100K tokens at ~4 chars/token

# Token budget compaction constants
DEFAULT_COMPACTION_THRESHOLD = 0.85
PRESERVE_RECENT_PAIRS = 5
DEFAULT_CONTEXT_WINDOW = 200_000  # All Claude 4.x models

# Map tool names to agent phases for progress reporting.
_TOOL_PHASE_MAP = {
    "read_file": AgentPhase.EXPLORING,
    "list_files": AgentPhase.EXPLORING,
    "search_codebase": AgentPhase.EXPLORING,
    "create_file": AgentPhase.CREATING,
    "edit_file": AgentPhase.EDITING,
    "run_tests": AgentPhase.TESTING,
    "run_command": AgentPhase.TESTING,
}

# ---------------------------------------------------------------------------
# Layer 1: Base rules (verbatim from AGENT_V3_UNIFIED_PLAN.md)
# ---------------------------------------------------------------------------

_LAYER_1_RULES = """\
You are CodeFRAME, an autonomous software engineering agent.

## Rules

- ALWAYS read a file before editing it. Never assume file contents.
- Make small, targeted edits. Do not rewrite entire files.
- For NEW files: use create_file. For EXISTING files: use edit_file with search/replace.
- Never edit_file on a file you haven't read in this session.
- Run tests after implementing each major feature, not after every line change.
- Keep solutions simple. Do not add features beyond what was asked.
- Do not change configuration files (pyproject.toml, package.json, etc.) unless
  the task explicitly requires it. If you must edit them, read first and make
  minimal, targeted changes.

## Code Quality

- No trailing whitespace
- Use 'raise X from Y' not bare 'raise X' after catching exceptions
- Follow the project's existing code style (read existing files first)
- All imports at the top of file, organized: stdlib -> third-party -> local

## When You're Done

Respond with a brief summary. Do not call any more tools.

## When You're Stuck

If you encounter a genuine blocker (conflicting requirements, missing credentials,
unclear business logic), explain clearly. Do NOT stop for trivial decisions.
"""


class ReactAgent:
    """ReAct agent that iterates: LLM call -> tool execution -> observe.

    Attributes:
        workspace: Target workspace.
        llm_provider: LLM provider for completions.
        max_iterations: Hard cap on LLM calls in the main loop.
        max_verification_retries: How many times to retry after failed gates.
    """

    def __init__(
        self,
        workspace: Workspace,
        llm_provider: LLMProvider,
        max_iterations: int = 30,
        max_verification_retries: int = 5,
        event_publisher: Optional[EventPublisher] = None,
        dry_run: bool = False,
        verbose: bool = False,
        on_event: Optional[Callable[[str, dict], None]] = None,
        debug: bool = False,
        output_logger: Optional[RunOutputLogger] = None,
        fix_coordinator: Optional[GlobalFixCoordinator] = None,
    ) -> None:
        self.workspace = workspace
        self.llm_provider = llm_provider
        self.max_iterations = max_iterations
        self.max_verification_retries = max_verification_retries
        self.event_publisher = event_publisher
        self.dry_run = dry_run
        self.verbose = verbose
        self.on_event = on_event
        self.debug = debug
        self.output_logger = output_logger
        self.fix_coordinator = fix_coordinator
        self.fix_tracker = FixAttemptTracker()
        self.blocker_id: Optional[str] = None

        # Token budget tracking for conversation compaction
        self._context_window_size: int = DEFAULT_CONTEXT_WINDOW
        self._compaction_threshold: float = self._read_compaction_threshold()
        self._total_tokens_used: int = 0
        self._compaction_count: int = 0

        # Debug logging setup
        self._debug_log_path: Optional[Path] = None
        self._failure_count = 0
        if debug:
            self._setup_debug_log()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, task_id: str) -> AgentStatus:
        """Execute the full agent workflow for a task.

        1. Load context
        2. Build system prompt (3 layers)
        3. Enter ReAct loop
        4. Run final verification (with retry)

        Returns:
            AgentStatus.COMPLETED — task finished successfully.
            AgentStatus.BLOCKED — a blocker was created (check self.blocker_id).
            AgentStatus.FAILED — max iterations or verification exhausted.
        """
        self._current_task_id = task_id
        self._verbose_print(f"[ReactAgent] Starting task {task_id}")
        self._emit(EventType.AGENT_STARTED, {"task_id": task_id})

        try:
            self._emit_progress(AgentPhase.EXPLORING, message="Loading task context")

            loader = ContextLoader(self.workspace)
            context = loader.load(task_id)

            self._emit_progress(AgentPhase.PLANNING, message="Building system prompt")

            system_prompt = self._build_system_prompt(context)

            status = self._react_loop(system_prompt)
            if status == AgentStatus.FAILED:
                self._emit(EventType.AGENT_FAILED, {
                    "task_id": task_id,
                    "reason": "max_iterations_reached",
                })
                self._emit_stream_error(task_id, "max_iterations_reached")
                return status

            if status == AgentStatus.BLOCKED:
                self._emit(EventType.AGENT_FAILED, {
                    "task_id": task_id,
                    "reason": "blocked",
                })
                self._emit_stream_error(task_id, "blocked")
                return AgentStatus.BLOCKED

            # Final verification with retry
            passed, reason = self._run_final_verification(system_prompt)
            if passed:
                self._verbose_print(f"[ReactAgent] Task {task_id} completed: {AgentStatus.COMPLETED.name}")
                self._emit(EventType.AGENT_COMPLETED, {"task_id": task_id})
                self._emit_stream_completion(task_id)
                return AgentStatus.COMPLETED

            if reason == "escalated_to_blocker":
                self._emit(EventType.AGENT_FAILED, {
                    "task_id": task_id,
                    "reason": "blocked",
                })
                self._emit_stream_error(task_id, "blocked")
                return AgentStatus.BLOCKED

            self._emit(EventType.AGENT_FAILED, {
                "task_id": task_id,
                "reason": "verification_failed",
            })
            self._emit_stream_error(task_id, "verification_failed")
            return AgentStatus.FAILED
        except Exception:
            logger.exception("ReactAgent.run() failed for task %s", task_id)
            self._emit(EventType.AGENT_FAILED, {
                "task_id": task_id,
                "reason": "exception",
            })
            self._emit_stream_error(task_id, "exception")
            return AgentStatus.FAILED

    # ------------------------------------------------------------------
    # ReAct loop
    # ------------------------------------------------------------------

    def _react_loop(self, system_prompt: str) -> AgentStatus:
        """Core ReAct loop: iterate LLM calls until text-only or max iterations.

        Returns AgentStatus.COMPLETED when the LLM responds with text only.
        Returns AgentStatus.BLOCKED when a blocker pattern is detected.
        Returns AgentStatus.FAILED when max_iterations is reached.
        """
        messages: list[dict] = []
        iterations = 0
        prompt_summary = system_prompt[:200]

        while iterations < self.max_iterations:
            self._verbose_print(f"[ReactAgent] Iteration {iterations + 1}/{self.max_iterations}")
            self._emit(EventType.AGENT_ITERATION_STARTED, {
                "task_id": self._current_task_id,
                "iteration": iterations,
                "system_prompt_summary": prompt_summary,
            })

            response = self.llm_provider.complete(
                messages=messages,
                purpose=Purpose.EXECUTION,
                tools=AGENT_TOOLS,
                temperature=0.0,
                system=system_prompt,
            )
            iterations += 1

            if not response.has_tool_calls:
                # Text-only response — agent thinks it's done.
                # Check for blocker patterns before accepting completion.
                # Use classify_error_for_blocker directly (not should_create_blocker)
                # because a text-only response means the LLM stopped calling tools.
                # All blocker categories — including external_service — are immediate
                # blockers here since the agent has no retry mechanism for text.
                text = response.content or ""
                category = classify_error_for_blocker(text)
                if category is not None:
                    reason = f"{category} issue detected in agent response"
                    self._create_text_blocker(text, reason)
                    self._emit(EventType.AGENT_ITERATION_COMPLETED, {
                        "task_id": self._current_task_id,
                        "iteration": iterations,
                        "has_tool_calls": False,
                    })
                    return AgentStatus.BLOCKED

                self._emit(EventType.AGENT_ITERATION_COMPLETED, {
                    "task_id": self._current_task_id,
                    "iteration": iterations,
                    "has_tool_calls": False,
                })
                return AgentStatus.COMPLETED

            # Build assistant message with tool calls
            assistant_msg: dict = {
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": [
                    {"id": tc.id, "name": tc.name, "input": tc.input}
                    for tc in response.tool_calls
                ],
            }
            messages.append(assistant_msg)

            # Execute each tool call and collect results
            tool_results = []
            for tc in response.tool_calls:
                phase = _TOOL_PHASE_MAP.get(tc.name, AgentPhase.EXPLORING)
                tc_file_path = tc.input.get("path", "") or tc.input.get("test_path", "")
                self._emit_progress(
                    phase,
                    tool_name=tc.name,
                    file_path=tc_file_path or None,
                    iteration=iterations,
                    message=f"{tc.name}: {tc_file_path}" if tc_file_path else tc.name,
                )

                self._verbose_print(f"[ReactAgent] Tool: {tc.name}")
                self._emit(EventType.AGENT_TOOL_DISPATCHED, {
                    "task_id": self._current_task_id,
                    "tool_name": tc.name,
                    "tool_call_id": tc.id,
                })

                result = self._execute_tool_with_lint(tc)

                self._emit(EventType.AGENT_TOOL_RESULT, {
                    "task_id": self._current_task_id,
                    "tool_call_id": result.tool_call_id,
                    "is_error": result.is_error,
                    "has_lint_errors": "LINT ERRORS" in result.content,
                })

                tool_results.append(
                    {
                        "tool_call_id": result.tool_call_id,
                        "content": result.content,
                        "is_error": result.is_error,
                    }
                )

                # Check error tool results for immediate blocker patterns
                if result.is_error:
                    self._failure_count += 1
                    category = classify_error_for_blocker(result.content)
                    if category in ("requirements", "access"):
                        self._create_text_blocker(
                            result.content,
                            f"{category} issue detected in tool result",
                        )
                        self._emit(EventType.AGENT_ITERATION_COMPLETED, {
                            "task_id": self._current_task_id,
                            "iteration": iterations,
                            "has_tool_calls": True,
                        })
                        return AgentStatus.BLOCKED

            # Add tool results as user message
            messages.append({"role": "user", "content": "", "tool_results": tool_results})

            self._emit(EventType.AGENT_ITERATION_COMPLETED, {
                "task_id": self._current_task_id,
                "iteration": iterations,
                "has_tool_calls": True,
                "tool_count": len(response.tool_calls),
            })

            # Compact conversation when approaching context window limit
            messages, compact_stats = self.compact_conversation(messages)
            if compact_stats.get("compacted"):
                self._verbose_print(
                    f"[ReactAgent] Compacted: saved {compact_stats['tokens_saved']} tokens "
                    f"(tiers: {compact_stats['tiers_used']})"
                )
                self._emit(EventType.AGENT_COMPACTION, compact_stats)

        # Exhausted iterations
        return AgentStatus.FAILED

    # ------------------------------------------------------------------
    # Final verification
    # ------------------------------------------------------------------

    def _run_final_verification(
        self, system_prompt: str
    ) -> tuple[bool, Optional[str]]:
        """Run gates and retry if they fail.

        When verification fails, runs a bounded mini ReAct loop (up to 5
        LLM turns per retry) so the agent can read files, apply fixes, and
        see tool results before the next gate check.

        Returns:
            (passed, error_summary_or_none)
        """
        max_fix_turns = 5  # LLM turns per retry attempt

        for attempt in range(1 + self.max_verification_retries):
            self._verbose_print("[ReactAgent] Running final verification...")
            self._emit_progress(
                AgentPhase.VERIFYING,
                message="Running verification gates",
                iteration=attempt,
            )
            gate_result = gates.run(self.workspace)
            if gate_result.passed:
                return (True, None)

            if attempt >= self.max_verification_retries:
                return (False, gate_result.summary)

            # Use structured error text for pattern matching (quick fixes,
            # fix_tracker dedup).  Fall back to the human-readable summary
            # when detailed_errors are not available.
            error_summary = gate_result.get_error_summary() or gate_result.summary

            # 1. Try quick fix first (no LLM needed)
            if self._try_quick_fix(error_summary):
                # Quick fix applied — re-run gates immediately (skip LLM)
                self.fix_tracker.record_attempt(error_summary, "quick_fix")
                self.fix_tracker.record_outcome(error_summary, "quick_fix", FixOutcome.SUCCESS)
                continue

            # 2. Record the gate failure and check for escalation
            self._failure_count += 1
            self.fix_tracker.record_attempt(error_summary, "verification_gate")
            self.fix_tracker.record_outcome(error_summary, "verification_gate", FixOutcome.FAILED)

            escalation = self.fix_tracker.should_escalate(error_summary)
            if escalation.should_escalate:
                self._create_escalation_blocker(error_summary, escalation)
                return (False, "escalated_to_blocker")

            # 3. Mini ReAct loop to fix the issues
            fix_messages: list[dict] = [
                {
                    "role": "user",
                    "content": (
                        f"Final verification failed: {error_summary}\n"
                        "Please fix the issues and respond when done."
                    ),
                }
            ]

            for _turn in range(max_fix_turns):
                response = self.llm_provider.complete(
                    messages=fix_messages,
                    purpose=Purpose.CORRECTION,
                    tools=AGENT_TOOLS,
                    temperature=0.0,
                    system=system_prompt,
                )

                if not response.has_tool_calls:
                    break  # Agent done fixing → re-run gates

                # Append assistant message with tool calls
                fix_messages.append(
                    {
                        "role": "assistant",
                        "content": response.content or "",
                        "tool_calls": [
                            {"id": tc.id, "name": tc.name, "input": tc.input}
                            for tc in response.tool_calls
                        ],
                    }
                )

                # Execute tools (with lint) and collect results
                tool_results = []
                for tc in response.tool_calls:
                    tc_file_path = tc.input.get("path", "") or tc.input.get("test_path", "")
                    self._emit_progress(
                        AgentPhase.FIXING,
                        tool_name=tc.name,
                        file_path=tc_file_path or None,
                        iteration=attempt,
                        message=f"Fixing: {tc.name}",
                    )
                    result = self._execute_tool_with_lint(tc)
                    tool_results.append(
                        {
                            "tool_call_id": result.tool_call_id,
                            "content": result.content,
                            "is_error": result.is_error,
                        }
                    )

                fix_messages.append(
                    {"role": "user", "content": "", "tool_results": tool_results}
                )

        return (False, "Verification retries exhausted")

    # ------------------------------------------------------------------
    # System prompt construction
    # ------------------------------------------------------------------

    def _build_system_prompt(self, context: TaskContext) -> str:
        """Build the 3-layer system prompt.

        Layer 1: Base rules (verbatim)
        Layer 2: Project preferences + tech stack + file tree summary
        Layer 3: Task title/description + PRD + answered blockers
        """
        sections: list[str] = []

        # Layer 1: Base rules
        sections.append(_LAYER_1_RULES)

        # Layer 2: Preferences, tech stack, file tree
        if context.preferences and context.preferences.has_preferences():
            pref_section = context.preferences.to_prompt_section()
            if pref_section:
                sections.append(pref_section)

        if context.tech_stack:
            sections.append(f"## Project Tech Stack\n{context.tech_stack}")

        if context.file_tree:
            tree_lines = [f"## Repository Structure ({len(context.file_tree)} files)"]
            for fi in context.file_tree[:50]:
                tree_lines.append(f"  {fi.path}")
            if len(context.file_tree) > 50:
                tree_lines.append(f"  ... and {len(context.file_tree) - 50} more")
            sections.append("\n".join(tree_lines))

        # Layer 3: Task info
        sections.append(f"## Current Task\n**Title:** {context.task.title}")
        if context.task.description:
            sections.append(f"**Description:** {context.task.description}")

        if context.prd:
            prd_content = context.prd.content[:5000]
            sections.append(f"## Requirements (PRD)\n{prd_content}")

        if context.answered_blockers:
            blocker_lines = ["## Previous Clarifications"]
            for b in context.answered_blockers:
                blocker_lines.append(f"**Q:** {b.question}")
                blocker_lines.append(f"**A:** {b.answer}")
            sections.append("\n".join(blocker_lines))

        # Intent preview for high-complexity tasks
        complexity = getattr(context.task, "complexity_score", None)
        if complexity is not None and complexity >= 4:
            sections.append(
                "## High-Complexity Task\n"
                "Before writing code, outline your plan: list the files you will "
                "create or modify, the approach, and key design decisions."
            )

        return "\n\n".join(sections)

    # ------------------------------------------------------------------
    # Tool execution with lint
    # ------------------------------------------------------------------

    # Must stay in sync with AGENT_TOOLS in tools.py.
    # Unknown tools default to write (safe: they get blocked in dry-run).
    # run_tests is classified as read because it doesn't modify workspace
    # files, even though it has side effects (process execution).
    _WRITE_TOOLS = {"edit_file", "create_file", "run_command"}
    _READ_TOOLS = {"read_file", "list_files", "search_codebase", "run_tests"}

    def _execute_tool_with_lint(self, tc) -> ToolResult:
        """Execute a tool call and append lint errors for edit/create.

        After a successful ``edit_file`` or ``create_file``, runs the
        appropriate linter (language-aware) and appends any errors to the
        tool result so the LLM can fix them immediately.

        In dry_run mode, write tools are skipped (returning a stub result)
        while read tools are executed normally.
        """
        if self.dry_run and tc.name not in self._READ_TOOLS:
            return ToolResult(
                tool_call_id=tc.id,
                content=f"[DRY RUN] Would execute {tc.name}",
            )

        result = execute_tool(tc, self.workspace.repo_path)

        if tc.name in ("edit_file", "create_file") and not result.is_error:
            lint_output = self._run_lint_on_file(tc.input.get("path", ""))
            if lint_output:
                result = ToolResult(
                    tool_call_id=result.tool_call_id,
                    content=result.content + f"\n\nLINT ERRORS (must fix before continuing):\n{lint_output}",
                    is_error=result.is_error,
                )

        return result

    def _run_lint_on_file(self, rel_path: str) -> str:
        """Run the appropriate linter on a single file within the workspace.

        Delegates to ``gates.run_lint_on_file()`` for language-aware linting.
        Returns lint error output, or empty string if clean / skipped.
        """
        if not rel_path:
            return ""

        file_path = (self.workspace.repo_path / rel_path).resolve()

        # Prevent path traversal outside workspace
        try:
            file_path.relative_to(self.workspace.repo_path.resolve())
        except ValueError:
            return ""

        if not file_path.exists():
            return ""

        self._emit(EventType.GATES_STARTED, {
            "gate": "lint",
            "path": rel_path,
        })

        check = gates.run_lint_on_file(file_path, self.workspace.repo_path)

        passed = check.status == gates.GateStatus.PASSED
        failed = check.status == gates.GateStatus.FAILED
        errored = check.status == gates.GateStatus.ERROR

        payload: dict = {
            "gate": "lint",
            "linter": check.name,
            "path": rel_path,
            "status": check.status.value,
            "passed": passed,
            "diagnostics": check.output[:500] if check.output else None,
        }
        if failed:
            payload["suggestions"] = [
                f"run the linter on `{rel_path}` locally to see violations",
                f"linter: {check.name}",
            ]
        elif errored:
            payload["suggestions"] = [
                f"lint check failed to run: {check.output[:100] if check.output else 'unknown error'}",
                f"verify `{check.name}` is installed and working",
            ]
        self._emit(EventType.GATES_COMPLETED, payload)

        # Only surface actionable lint failures to the LLM — not
        # infrastructure errors (ERROR) or skipped checks (SKIPPED).
        if failed:
            return check.output[:2000]

        return ""

    # ------------------------------------------------------------------
    # Verbose and debug logging
    # ------------------------------------------------------------------

    def _verbose_print(self, message: str) -> None:
        """Print message to stdout (if verbose) and to output log file.

        The output log file is always written to (if logger provided) to enable
        streaming via ``cf work follow``, even when verbose=False.
        """
        if self.verbose:
            print(message)
        if self.output_logger:
            self.output_logger.write(message + "\n")

    def _setup_debug_log(self) -> None:
        """Set up the debug log file in workspace directory."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._debug_log_path = self.workspace.repo_path / f".codeframe_debug_react_{timestamp}.log"

        with open(self._debug_log_path, "w") as f:
            f.write("=" * 80 + "\n")
            f.write("CodeFRAME ReactAgent Debug Log\n")
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
        """Write to the debug log file."""
        if not self._debug_log_path:
            return

        if not always and self._failure_count == 0 and level == "DEBUG":
            return

        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] [{level}] {message}\n"

        with open(self._debug_log_path, "a") as f:
            f.write(line)
            if data:
                for key, value in data.items():
                    val_str = str(value)
                    if len(val_str) > 500:
                        val_str = val_str[:500] + "... [TRUNCATED]"
                    f.write(f"  {key}: {val_str}\n")
                f.write("\n")

    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------

    def _emit(self, event_type: str, payload: dict) -> None:
        """Emit an event, suppressing failures to keep the agent running."""
        try:
            events.emit_for_workspace(
                self.workspace, event_type, payload, print_event=False,
            )
        except Exception:
            logger.debug("Failed to emit %s event", event_type, exc_info=True)
        if self.on_event is not None:
            try:
                self.on_event(event_type, payload)
            except Exception:
                logger.debug("on_event callback failed for %s", event_type, exc_info=True)

    def _emit_progress(
        self,
        phase: str,
        *,
        step: int = 0,
        total_steps: int = 0,
        message: str | None = None,
        tool_name: str | None = None,
        file_path: str | None = None,
        iteration: int | None = None,
    ) -> None:
        """Emit a ProgressEvent via the event_publisher, if present."""
        if self.event_publisher is None:
            return
        try:
            self.event_publisher.publish_sync(
                self._current_task_id,
                ProgressEvent(
                    task_id=self._current_task_id,
                    phase=phase,
                    step=step,
                    total_steps=total_steps,
                    message=message,
                    tool_name=tool_name,
                    file_path=file_path,
                    iteration=iteration,
                ),
            )
        except Exception:
            logger.debug("Failed to emit progress event", exc_info=True)

    def _emit_stream_completion(self, task_id: str) -> None:
        """Publish CompletionEvent and close the SSE stream for subscribers."""
        if self.event_publisher is None:
            return
        try:
            self.event_publisher.publish_sync(
                task_id,
                CompletionEvent(
                    task_id=task_id,
                    status="completed",
                    duration_seconds=0,
                ),
            )
        except Exception:
            logger.debug("Failed to emit stream completion", exc_info=True)
        finally:
            try:
                self.event_publisher.complete_task_sync(task_id)
            except Exception:
                logger.debug("Failed to close task stream", exc_info=True)

    def _emit_stream_error(self, task_id: str, reason: str) -> None:
        """Publish ErrorEvent and close the SSE stream for subscribers."""
        if self.event_publisher is None:
            return
        try:
            self.event_publisher.publish_sync(
                task_id,
                ErrorEvent(
                    task_id=task_id,
                    error_type="agent_failed",
                    error=reason,
                ),
            )
        except Exception:
            logger.debug("Failed to emit stream error", exc_info=True)
        finally:
            try:
                self.event_publisher.complete_task_sync(task_id)
            except Exception:
                logger.debug("Failed to close task stream", exc_info=True)

    # ------------------------------------------------------------------
    # Blocker creation helpers
    # ------------------------------------------------------------------

    def _create_text_blocker(self, text: str, reason: str) -> None:
        """Create a blocker from LLM text or tool error content.

        Stores the blocker ID on ``self.blocker_id`` so runtime can link
        the run record to the blocker.  If creation fails the exception
        propagates — callers in ``run()`` catch it and return FAILED.
        """
        question = (
            f"Agent detected a blocker: {reason}\n\n"
            f"Context:\n{text[:500]}"
        )
        blocker = blockers.create(
            workspace=self.workspace,
            question=question,
            task_id=self._current_task_id,
        )
        self.blocker_id = blocker.id

    def _create_escalation_blocker(
        self, error: str, escalation: EscalationDecision
    ) -> None:
        """Create a blocker when fix_tracker recommends escalation.

        Stores the blocker ID on ``self.blocker_id`` so runtime can link
        the run record to the blocker.  If creation fails the exception
        propagates — callers in ``run()`` catch it and return FAILED.
        """
        context = self.fix_tracker.get_blocker_context(error)
        attempted = context.get("attempted_fixes", [])
        attempted_str = "\n".join(f"  - {f}" for f in attempted) if attempted else "  (none)"

        question = (
            f"Verification keeps failing and automated fixes are not working.\n\n"
            f"Error: {error[:300]}\n\n"
            f"Reason for escalation: {escalation.reason}\n\n"
            f"Fixes already attempted:\n{attempted_str}\n\n"
            f"Total failures in this run: {context.get('total_run_failures', 0)}\n\n"
            f"Please investigate and provide guidance."
        )
        blocker = blockers.create(
            workspace=self.workspace,
            question=question,
            task_id=self._current_task_id,
        )
        self.blocker_id = blocker.id

    def _try_quick_fix(self, error_summary: str) -> bool:
        """Attempt a pattern-based quick fix for the gate error.

        Returns True if a fix was successfully applied.
        """
        fix = find_quick_fix(error_summary, repo_path=self.workspace.repo_path)
        if fix is None:
            return False

        success, _ = apply_quick_fix(fix, self.workspace.repo_path)
        return success

    # ------------------------------------------------------------------
    # Token budget and compaction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_compaction_threshold() -> float:
        """Read compaction threshold from env var, with validation and clamping."""
        raw = os.environ.get("CODEFRAME_REACT_COMPACT_THRESHOLD")
        if raw is None:
            return DEFAULT_COMPACTION_THRESHOLD
        try:
            value = float(raw)
        except (ValueError, TypeError):
            return DEFAULT_COMPACTION_THRESHOLD
        # Clamp to valid range
        return max(0.5, min(0.95, value))

    def _estimate_message_tokens(self, message: dict) -> int:
        """Estimate token count for a single message using len(str)/4 heuristic."""
        tokens = 0
        content = message.get("content", "")
        if content:
            tokens += len(content) // 4

        tool_calls = message.get("tool_calls")
        if tool_calls:
            tokens += len(json.dumps(tool_calls)) // 4

        tool_results = message.get("tool_results")
        if tool_results:
            tokens += len(json.dumps(tool_results)) // 4

        return tokens

    def _estimate_conversation_tokens(self, messages: list[dict]) -> int:
        """Estimate total tokens across all messages. Updates _total_tokens_used."""
        total = sum(self._estimate_message_tokens(m) for m in messages)
        self._total_tokens_used = total
        return total

    def _should_compact(self, messages: list[dict]) -> bool:
        """Return True if estimated token usage >= threshold ratio of context window."""
        tokens = self._estimate_conversation_tokens(messages)
        ratio = tokens / self._context_window_size if self._context_window_size > 0 else 0
        return ratio >= self._compaction_threshold

    # ------------------------------------------------------------------
    # 3-tier compaction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_tool_name_from_pair(assistant_msg: dict) -> str:
        """Extract tool name from an assistant message's tool_calls."""
        tool_calls = assistant_msg.get("tool_calls", [])
        if tool_calls:
            return tool_calls[0].get("name", "")
        return ""

    def _compact_tool_results(
        self, messages: list[dict]
    ) -> tuple[list[dict], int]:
        """Tier 1: Replace verbose tool result content with short summaries.

        Iterates through older messages (outside PRESERVE_RECENT_PAIRS zone)
        and replaces verbose tool result content with a short summary.
        Error results (is_error=True) are preserved intact.

        Returns (modified messages, tokens_saved).
        """
        preserve_count = PRESERVE_RECENT_PAIRS * 2
        if len(messages) <= preserve_count:
            return messages, 0

        saved = 0
        cutoff = len(messages) - preserve_count

        for i in range(cutoff):
            msg = messages[i]
            tool_results = msg.get("tool_results")
            if not tool_results:
                continue

            # Find tool name from preceding assistant message
            tool_name = ""
            if i > 0:
                tool_name = self._extract_tool_name_from_pair(messages[i - 1])

            new_results = []
            for tr in tool_results:
                if tr.get("is_error"):
                    new_results.append(tr)
                    continue

                old_content = tr.get("content", "")
                if not old_content:
                    new_results.append(tr)
                    continue

                first_line = old_content.split("\n")[0][:80]
                summary = f"[Compacted] {tool_name}: {first_line}..."
                old_tokens = len(old_content) // 4
                new_tokens = len(summary) // 4
                saved += max(0, old_tokens - new_tokens)
                new_results.append({
                    "tool_call_id": tr["tool_call_id"],
                    "content": summary,
                    "is_error": False,
                })

            messages[i] = {**msg, "tool_results": new_results}

        return messages, saved

    def _remove_intermediate_steps(
        self, messages: list[dict]
    ) -> tuple[list[dict], int]:
        """Tier 2: Remove redundant assistant+user pairs.

        Removes pairs where:
        - The same file was read again later without an intervening edit
        - Test output shows all tests passed

        Preserves the last PRESERVE_RECENT_PAIRS*2 messages.
        Returns (modified messages, tokens_saved).
        """
        preserve_count = PRESERVE_RECENT_PAIRS * 2
        if len(messages) <= preserve_count:
            return messages, 0

        cutoff = len(messages) - preserve_count
        indices_to_remove: set[int] = set()

        # Build a map of file reads and edits in the compactable zone
        # Process pairs: assistant at even index, user at odd index
        for i in range(0, cutoff - 1, 2):
            assistant = messages[i]
            user = messages[i + 1]
            tool_calls = assistant.get("tool_calls", [])
            if not tool_calls:
                continue

            tc = tool_calls[0]
            tool_name = tc.get("name", "")
            file_path = tc.get("input", {}).get("path", "")

            # Check for redundant file reads
            if tool_name == "read_file" and file_path:
                # Look for a later read of the same file without an edit in between
                has_edit_between = False
                has_later_read = False
                for j in range(i + 2, len(messages) - 1, 2):
                    later_assistant = messages[j]
                    later_tcs = later_assistant.get("tool_calls", [])
                    if not later_tcs:
                        continue
                    later_name = later_tcs[0].get("name", "")
                    later_path = later_tcs[0].get("input", {}).get("path", "")
                    if later_name in ("edit_file", "create_file") and later_path == file_path:
                        has_edit_between = True
                        break
                    if later_name == "read_file" and later_path == file_path:
                        has_later_read = True
                        break

                if has_later_read and not has_edit_between:
                    indices_to_remove.add(i)
                    indices_to_remove.add(i + 1)

            # Check for passed test results
            if tool_name in ("run_tests", "run_command"):
                tool_results = user.get("tool_results", [])
                for tr in tool_results:
                    content = tr.get("content", "")
                    if not tr.get("is_error") and ("passed" in content.lower()):
                        indices_to_remove.add(i)
                        indices_to_remove.add(i + 1)
                        break

        if not indices_to_remove:
            return messages, 0

        saved = sum(
            self._estimate_message_tokens(messages[i]) for i in indices_to_remove
        )
        result = [m for idx, m in enumerate(messages) if idx not in indices_to_remove]
        return result, saved

    def _summarize_old_messages(
        self, messages: list[dict], target_tokens: int
    ) -> tuple[list[dict], int]:
        """Tier 3: Replace oldest messages with a single summary message.

        Extracts file paths, error messages, and architectural keywords
        from old messages and creates a compact summary.

        Preserves the last PRESERVE_RECENT_PAIRS*2 messages.
        Returns (modified messages, tokens_saved).
        """
        preserve_count = PRESERVE_RECENT_PAIRS * 2
        if len(messages) <= preserve_count:
            return messages, 0

        cutoff = len(messages) - preserve_count
        old_messages = messages[:cutoff]
        recent_messages = messages[cutoff:]

        # Extract preserved information from old messages
        file_paths: list[str] = []
        errors: list[str] = []
        decisions: list[str] = []

        for msg in old_messages:
            # Extract file paths from tool calls
            for tc in msg.get("tool_calls", []):
                path = tc.get("input", {}).get("path", "")
                if path and path not in file_paths:
                    file_paths.append(path)

            # Extract errors from tool results
            for tr in msg.get("tool_results", []):
                if tr.get("is_error"):
                    errors.append(tr.get("content", "")[:100])

            # Extract architectural keywords from assistant content
            content = msg.get("content", "")
            if msg.get("role") == "assistant" and content:
                for keyword in ("architecture", "design", "pattern", "decision"):
                    if keyword in content.lower():
                        # Extract a snippet around the keyword
                        idx = content.lower().index(keyword)
                        snippet = content[max(0, idx - 20):idx + 50].strip()
                        if snippet not in decisions:
                            decisions.append(snippet)
                        break

        # Build summary
        parts = ["[Summary] Previous context:"]
        if file_paths:
            parts.append(f"analyzed {len(file_paths)} files ({', '.join(file_paths[:10])})")
        if errors:
            parts.append(f"{len(errors)} errors encountered ({'; '.join(errors[:3])})")
        if decisions:
            parts.append(f"architectural decisions: {'; '.join(decisions[:3])}")

        summary_content = ", ".join(parts) if len(parts) > 1 else parts[0] + " (no details extracted)"
        summary_msg = {"role": "user", "content": summary_content}

        saved = sum(self._estimate_message_tokens(m) for m in old_messages)
        saved -= self._estimate_message_tokens(summary_msg)
        saved = max(0, saved)

        return [summary_msg] + recent_messages, saved

    def compact_conversation(
        self, messages: list[dict]
    ) -> tuple[list[dict], dict]:
        """Orchestrate 3-tier compaction when conversation exceeds token budget.

        Runs tiers in order (1 -> 2 -> 3), stopping when under threshold.
        Returns (messages, stats_dict).
        """
        if not self._should_compact(messages):
            return messages, {"compacted": False}

        tokens_before = self._estimate_conversation_tokens(messages)
        tiers_used: list[str] = []

        # Tier 1: Compact tool results
        messages, saved = self._compact_tool_results(messages)
        if saved > 0:
            tiers_used.append("tier1_tool_results")
        if not self._should_compact(messages):
            return self._finalize_compaction(
                messages, tokens_before, tiers_used
            )

        # Tier 2: Remove intermediate steps
        messages, saved = self._remove_intermediate_steps(messages)
        if saved > 0:
            tiers_used.append("tier2_intermediate")
        if not self._should_compact(messages):
            return self._finalize_compaction(
                messages, tokens_before, tiers_used
            )

        # Tier 3: Summarize old messages
        target = int(self._context_window_size * self._compaction_threshold)
        messages, saved = self._summarize_old_messages(messages, target)
        if saved > 0:
            tiers_used.append("tier3_summary")

        return self._finalize_compaction(messages, tokens_before, tiers_used)

    def _finalize_compaction(
        self,
        messages: list[dict],
        tokens_before: int,
        tiers_used: list[str],
    ) -> tuple[list[dict], dict]:
        """Build stats dict and increment counter after compaction."""
        self._compaction_count += 1
        tokens_after = self._estimate_conversation_tokens(messages)
        stats = {
            "compacted": True,
            "tokens_before": tokens_before,
            "tokens_after": tokens_after,
            "tokens_saved": tokens_before - tokens_after,
            "tiers_used": tiers_used,
            "compaction_number": self._compaction_count,
        }
        logger.info(
            "Compaction #%d: %d -> %d tokens (saved %d, tiers: %s)",
            stats["compaction_number"],
            stats["tokens_before"],
            stats["tokens_after"],
            stats["tokens_saved"],
            stats["tiers_used"],
        )
        return messages, stats

    def get_token_stats(self, messages: list[dict]) -> dict:
        """Return current token usage statistics."""
        total = self._estimate_conversation_tokens(messages)
        return {
            "total_tokens": total,
            "percentage_used": total / self._context_window_size if self._context_window_size > 0 else 0,
            "compaction_count": self._compaction_count,
            "context_window_size": self._context_window_size,
        }

    # ------------------------------------------------------------------
    # Message history management (deprecated — use compact_conversation)
    # ------------------------------------------------------------------

    @staticmethod
    def _trim_messages(messages: list[dict]) -> list[dict]:
        """Drop oldest assistant+user pairs when history exceeds the token budget.

        Preserves the first complete pair (messages[0:2]) and the most recent
        pair, removing whole assistant+user pairs from index 2 onward so no
        assistant message is ever left without its corresponding user/result.
        """
        total = sum(len(str(m)) for m in messages)
        if total <= _MAX_HISTORY_CHARS:
            return messages

        # Keep first pair (0,1) + at least one trailing pair → need > 4
        while len(messages) > 4 and total > _MAX_HISTORY_CHARS:
            removed = messages.pop(2)
            total -= len(str(removed))
            # Remove the following user message to keep the pair intact
            if len(messages) > 2 and messages[2].get("role") == "user":
                removed = messages.pop(2)
                total -= len(str(removed))

        return messages
