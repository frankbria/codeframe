"""ReAct-style agent for CodeFRAME v3.

Implements a tool-use loop where the LLM reasons, acts (via tools),
and observes results iteratively until the task is complete.

This module is headless - no FastAPI or HTTP dependencies.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Optional

from codeframe.adapters.llm.base import LLMProvider, Purpose, ToolResult
from codeframe.core import gates
from codeframe.core.agent import AgentStatus
from codeframe.core.context import ContextLoader, TaskContext
from codeframe.core.tools import AGENT_TOOLS, execute_tool
from codeframe.core.workspace import Workspace

logger = logging.getLogger(__name__)

# Rough token budget for conversation history to avoid overflowing LLM context.
_MAX_HISTORY_CHARS = 400_000  # ~100K tokens at ~4 chars/token

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
    ) -> None:
        self.workspace = workspace
        self.llm_provider = llm_provider
        self.max_iterations = max_iterations
        self.max_verification_retries = max_verification_retries

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
            AgentStatus.COMPLETED or AgentStatus.FAILED
        """
        try:
            loader = ContextLoader(self.workspace)
            context = loader.load(task_id)

            system_prompt = self._build_system_prompt(context)

            status = self._react_loop(system_prompt)
            if status == AgentStatus.FAILED:
                return status

            # Final verification with retry
            passed, _ = self._run_final_verification(system_prompt)
            if passed:
                return AgentStatus.COMPLETED
            return AgentStatus.FAILED
        except Exception:
            logger.exception("ReactAgent.run() failed for task %s", task_id)
            return AgentStatus.FAILED

    # ------------------------------------------------------------------
    # ReAct loop
    # ------------------------------------------------------------------

    def _react_loop(self, system_prompt: str) -> AgentStatus:
        """Core ReAct loop: iterate LLM calls until text-only or max iterations.

        Returns AgentStatus.COMPLETED when the LLM responds with text only.
        Returns AgentStatus.FAILED when max_iterations is reached.
        """
        messages: list[dict] = []
        iterations = 0

        while iterations < self.max_iterations:
            response = self.llm_provider.complete(
                messages=messages,
                purpose=Purpose.EXECUTION,
                tools=AGENT_TOOLS,
                temperature=0.0,
                system=system_prompt,
            )
            iterations += 1

            if not response.has_tool_calls:
                # Text-only response — agent thinks it's done
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
                result = self._execute_tool_with_lint(tc)

                tool_results.append(
                    {
                        "tool_call_id": result.tool_call_id,
                        "content": result.content,
                        "is_error": result.is_error,
                    }
                )

            # Add tool results as user message
            messages.append({"role": "user", "tool_results": tool_results})

            # Trim old messages if history grows too large
            messages = self._trim_messages(messages)

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
            gate_result = gates.run(self.workspace)
            if gate_result.passed:
                return (True, None)

            if attempt >= self.max_verification_retries:
                return (False, gate_result.summary)

            # Mini ReAct loop to fix the issues
            error_summary = gate_result.summary
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
                    result = self._execute_tool_with_lint(tc)
                    tool_results.append(
                        {
                            "tool_call_id": result.tool_call_id,
                            "content": result.content,
                            "is_error": result.is_error,
                        }
                    )

                fix_messages.append(
                    {"role": "user", "tool_results": tool_results}
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

    def _execute_tool_with_lint(self, tc) -> ToolResult:
        """Execute a tool call and append ruff lint errors for edit/create."""
        result = execute_tool(tc, self.workspace.repo_path)

        if tc.name in ("edit_file", "create_file") and not result.is_error:
            lint_output = self._run_ruff_on_file(tc.input.get("path", ""))
            if lint_output:
                result = ToolResult(
                    tool_call_id=result.tool_call_id,
                    content=result.content + f"\n\nLINT ERRORS (must fix before continuing):\n{lint_output}",
                    is_error=result.is_error,
                )

        return result

    def _run_ruff_on_file(self, rel_path: str) -> str:
        """Run ruff check on a single file within the workspace.

        Returns lint error output, or empty string if clean.
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

        try:
            result = subprocess.run(
                ["ruff", "check", str(file_path)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.workspace.repo_path),
            )
            if result.returncode != 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return ""

    # ------------------------------------------------------------------
    # Message history management
    # ------------------------------------------------------------------

    @staticmethod
    def _trim_messages(messages: list[dict]) -> list[dict]:
        """Drop oldest message pairs when history exceeds the token budget.

        Preserves messages[0] (initial context from the first LLM turn) and
        trims older pairs from the middle, always removing assistant+user
        pairs together to maintain valid turn structure.
        """
        total = sum(len(str(m)) for m in messages)
        if total <= _MAX_HISTORY_CHARS:
            return messages

        # Drop oldest pairs starting from index 1 (preserve first message)
        while len(messages) > 3 and total > _MAX_HISTORY_CHARS:
            removed = messages.pop(1)
            total -= len(str(removed))
            if len(messages) > 1 and messages[1].get("role") == "user":
                removed = messages.pop(1)
                total -= len(str(removed))

        return messages
