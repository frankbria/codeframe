"""Task context packager for assembling rich prompts for agent adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from codeframe.core.adapters.agent_adapter import AgentContext
from codeframe.core.context import ContextLoader, TaskContext
from codeframe.core.workspace import Workspace


@dataclass
class PackagedContext:
    """Packaged task context ready for an agent adapter."""

    prompt: str
    context: TaskContext


class TaskContextPackager:
    """Assembles rich task prompts from CodeFRAME context for any agent adapter.

    Wraps ContextLoader and appends gate requirements so external agents
    know what verification criteria they must satisfy.
    """

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace
        self._loader = ContextLoader(workspace)

    def build(
        self,
        task_id: str,
        gate_names: Optional[list[str]] = None,
        attempt: int = 0,
        previous_errors: Optional[list[str]] = None,
    ) -> PackagedContext:
        """Build a rich prompt and context for the given task.

        Args:
            task_id: CodeFRAME task identifier.
            gate_names: Optional list of gate names that will run post-execution.
                        If None, uses default gates (pytest, ruff).
            attempt: Retry attempt number (0 = first attempt).
            previous_errors: Errors from previous attempts.

        Returns:
            PackagedContext with assembled prompt and raw TaskContext.
        """
        context = self._loader.load(task_id)

        prompt_parts = [context.to_prompt_context()]

        if attempt > 0 and previous_errors:
            prompt_parts.append(self._build_retry_section(attempt, previous_errors))

        gates = gate_names or ["pytest", "ruff"]
        prompt_parts.append(self._build_gate_section(gates))
        prompt_parts.append(self._build_instructions_section())

        return PackagedContext(
            prompt="\n".join(prompt_parts),
            context=context,
        )

    def build_agent_context(
        self,
        task_id: str,
        attempt: int = 0,
        previous_errors: Optional[list[str]] = None,
        gate_names: Optional[list[str]] = None,
    ) -> AgentContext:
        """Assemble an AgentContext from all CodeFrame sources.

        Bridges TaskContext (internal, Python objects) to AgentContext
        (protocol, all strings/primitives) for consumption by any adapter.

        Args:
            task_id: CodeFRAME task identifier.
            attempt: Retry attempt number (0 = first attempt).
            previous_errors: Errors from previous attempts.
            gate_names: Optional gate names override.

        Returns:
            AgentContext populated from TaskContext fields.
        """
        context = self._loader.load(task_id)
        gates = gate_names or ["pytest", "ruff"]

        prd_content = None
        if context.prd is not None:
            prd_content = context.prd.content

        project_preferences = None
        if context.preferences and context.preferences.has_preferences():
            section = context.preferences.to_prompt_section()
            if section:
                project_preferences = section

        blocker_history = [
            f"Q: {b.question}\nA: {b.answer}"
            for b in context.answered_blockers
        ]

        relevant_files = [fi.path for fi in context.relevant_files]

        file_contents = {f.path: f.content for f in context.loaded_files}

        return AgentContext(
            task_id=task_id,
            task_title=context.task.title,
            task_description=context.task.description or "",
            prd_content=prd_content,
            tech_stack=context.tech_stack,
            project_preferences=project_preferences,
            relevant_files=relevant_files,
            file_contents=file_contents,
            blocker_history=blocker_history,
            verification_gates=gates,
            attempt=attempt,
            previous_errors=previous_errors or [],
        )

    def to_file_list(self, packaged: PackagedContext) -> list[str]:
        """Extract the list of files the agent should focus on.

        Args:
            packaged: A previously built PackagedContext.

        Returns:
            List of relevant file paths sorted by relevance score.
        """
        return [fi.path for fi in packaged.context.relevant_files]

    def to_task_file(self, packaged: PackagedContext, path: Path) -> Path:
        """Write the assembled prompt to a file for file-based engines.

        Args:
            packaged: A previously built PackagedContext.
            path: Where to write the task file.

        Returns:
            The path that was written to.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(packaged.prompt, encoding="utf-8")
        return path

    def _build_retry_section(self, attempt: int, errors: list[str]) -> str:
        """Build the retry context section."""
        lines = [
            "",
            "## Previous Attempt Errors",
            "",
            f"**Attempt {attempt}** — previous attempt(s) failed with:",
            "",
        ]
        for error in errors:
            lines.append(f"- {error}")
        lines.append("")
        lines.append(
            "Review these errors carefully. Do NOT repeat the same approach "
            "that caused them."
        )
        lines.append("")
        return "\n".join(lines)

    def _build_gate_section(self, gate_names: list[str]) -> str:
        """Build the gate requirements section."""
        lines = [
            "",
            "## Verification Gates",
            "",
            "After you complete the task, the following verification gates "
            "will run automatically:",
            "",
        ]
        for gate in gate_names:
            if gate == "pytest":
                lines.append(
                    "- **pytest**: All tests must pass. "
                    "Run `pytest` to verify before finishing."
                )
            elif gate == "ruff":
                lines.append(
                    "- **ruff**: Code must pass linting. "
                    "Run `ruff check .` to verify."
                )
            else:
                lines.append(f"- **{gate}**: Must pass.")
        lines.append("")
        lines.append(
            "Ensure your changes satisfy ALL gates before reporting completion."
        )
        lines.append("")
        return "\n".join(lines)

    def _build_instructions_section(self) -> str:
        """Build general execution instructions for the agent."""
        return "\n".join(
            [
                "## Execution Instructions",
                "",
                "- Make only the changes necessary to complete the task",
                "- Do not modify unrelated files",
                "- Follow existing code patterns and conventions",
                "- If you encounter a blocker you cannot resolve, report it clearly",
                "",
            ]
        )
