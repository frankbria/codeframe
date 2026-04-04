"""Agent adapter protocol for delegating task execution to external coding agents.

Defines the interface that any coding agent (Claude Code, Codex, Aider, built-in)
must implement to be used as a CodeFrame execution engine, plus the supporting
types for context, results, events, and token tracking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Literal, Protocol, runtime_checkable


class AgentResultStatus(str, Enum):
    """Terminal status from an agent execution."""

    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"


@dataclass
class AdapterTokenUsage:
    """Lightweight token usage for adapter results."""

    input_tokens: int
    output_tokens: int
    model: str | None = None
    cost_usd: float | None = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class AgentContext:
    """Everything CodeFrame provides to an execution engine."""

    task_id: str
    task_title: str
    task_description: str
    prd_content: str | None = None
    tech_stack: str | None = None
    project_preferences: str | None = None
    relevant_files: list[str] = field(default_factory=list)
    file_contents: dict[str, str] = field(default_factory=dict)
    blocker_history: list[str] = field(default_factory=list)
    dependency_context: str | None = None
    verification_gates: list[str] = field(default_factory=list)
    attempt: int = 0
    previous_errors: list[str] = field(default_factory=list)


@dataclass
class AgentResult:
    """Result from an agent adapter execution."""

    status: Literal["completed", "failed", "blocked"]
    output: str = ""
    modified_files: list[str] = field(default_factory=list)
    error: str | None = None
    blocker_question: str | None = None
    token_usage: AdapterTokenUsage | None = None
    duration_ms: int = 0
    cloud_metadata: dict | None = None


@dataclass
class AgentEvent:
    """Progress event emitted during agent execution."""

    type: str  # "progress", "tool_call", "output", "error"
    data: dict = field(default_factory=dict)
    message: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


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
