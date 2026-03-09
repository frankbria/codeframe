"""Agent adapter protocol for delegating task execution to external coding agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal, Protocol, runtime_checkable


@dataclass
class AgentResult:
    """Result from an agent adapter execution."""

    status: Literal["completed", "failed", "blocked"]
    output: str = ""
    modified_files: list[str] = field(default_factory=list)
    error: str | None = None
    blocker_question: str | None = None


@dataclass
class AgentEvent:
    """Progress event emitted during agent execution."""

    type: str  # "progress", "tool_call", "output", "error"
    data: dict = field(default_factory=dict)


@runtime_checkable
class AgentAdapter(Protocol):
    """Protocol for agent execution engines.

    Any coding agent (Claude Code, OpenCode, Codex, etc.) must implement
    this interface to be used as a CodeFRAME execution engine.
    """

    @property
    def name(self) -> str:
        """Engine name (e.g., 'claude-code', 'opencode')."""
        ...

    def run(
        self,
        task_id: str,
        prompt: str,
        workspace_path: Path,
        on_event: Callable[[AgentEvent], None] | None = None,
    ) -> AgentResult:
        """Execute a task and return the result.

        Args:
            task_id: CodeFRAME task identifier
            prompt: Rich context prompt assembled by TaskContextPackager
            workspace_path: Path to the workspace/repo root
            on_event: Optional callback for streaming progress events

        Returns:
            AgentResult with status, output, and modified files
        """
        ...
