"""Agent adapter protocol for CodeFRAME.

Defines the interface that any coding agent (Claude Code, Codex, Aider, built-in)
must implement to be used as a CodeFrame execution engine.

This module is headless - no FastAPI or HTTP dependencies.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterator, Protocol, runtime_checkable


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
    """What every execution engine returns to CodeFrame."""

    status: AgentResultStatus
    summary: str
    files_modified: list[str] = field(default_factory=list)
    files_created: list[str] = field(default_factory=list)
    error: str | None = None
    blocker_question: str | None = None
    token_usage: AdapterTokenUsage | None = None
    duration_ms: int = 0


@dataclass
class AgentEvent:
    """Progress event yielded during agent execution."""

    type: str
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)


@runtime_checkable
class AgentAdapter(Protocol):
    """Interface for any coding agent that CodeFrame can orchestrate."""

    def execute(
        self,
        task_prompt: str,
        workspace_path: Path,
        context: AgentContext,
        timeout_ms: int = 3_600_000,
    ) -> AgentResult: ...

    def stream_events(self) -> Iterator[AgentEvent]: ...

    @property
    def name(self) -> str: ...

    @property
    def requires_api_key(self) -> dict[str, str]: ...
