"""Task context packager for assembling rich prompts for agent adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

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
        self, task_id: str, gate_names: Optional[list[str]] = None
    ) -> PackagedContext:
        """Build a rich prompt and context for the given task.

        Args:
            task_id: CodeFRAME task identifier.
            gate_names: Optional list of gate names that will run post-execution.
                        If None, uses default gates (pytest, ruff).

        Returns:
            PackagedContext with assembled prompt and raw TaskContext.
        """
        context = self._loader.load(task_id)

        prompt_parts = [context.to_prompt_context()]

        gates = gate_names or ["pytest", "ruff"]
        prompt_parts.append(self._build_gate_section(gates))
        prompt_parts.append(self._build_instructions_section())

        return PackagedContext(
            prompt="\n".join(prompt_parts),
            context=context,
        )

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
