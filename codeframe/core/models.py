"""Core data models for CodeFRAME."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator


class TaskStatus(Enum):
    """Task execution status."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


# Valid task status values for API validation and database constraints
VALID_TASK_STATUSES: frozenset[str] = frozenset(s.value for s in TaskStatus)


class AgentMaturity(Enum):
    """Agent maturity levels based on Situational Leadership II."""

    D1 = "directive"  # Low skill, needs step-by-step
    D2 = "coaching"  # Some skill, needs guidance
    D3 = "supporting"  # High skill, needs autonomy
    D4 = "delegating"  # Expert, full ownership


class ProjectStatus(Enum):
    """Project lifecycle status."""

    INIT = "init"
    PLANNING = "planning"
    RUNNING = "running"  # cf-10: Agent actively working on project
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"  # Agent terminated, project not active
    COMPLETED = "completed"


class ProjectPhase(Enum):
    """Project workflow phase."""

    DISCOVERY = "discovery"
    PLANNING = "planning"
    ACTIVE = "active"
    REVIEW = "review"
    COMPLETE = "complete"


class SourceType(Enum):
    """Project source type."""

    GIT_REMOTE = "git_remote"
    LOCAL_PATH = "local_path"
    UPLOAD = "upload"
    EMPTY = "empty"


@dataclass
class Project:
    """Represents a CodeFRAME project.

    Projects are the top-level container for issues and tasks. Each project
    has a managed workspace, optional source tracking, and workflow state.
    """

    id: Optional[int] = None
    name: str = ""
    description: str = ""
    source_type: SourceType = SourceType.EMPTY
    source_location: Optional[str] = None
    source_branch: str = "main"
    workspace_path: str = ""
    git_initialized: bool = False
    current_commit: Optional[str] = None
    status: ProjectStatus = ProjectStatus.INIT
    phase: ProjectPhase = ProjectPhase.DISCOVERY
    created_at: datetime = field(default_factory=datetime.now)
    paused_at: Optional[datetime] = None
    config: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert Project to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "source_type": self.source_type.value,
            "source_location": self.source_location,
            "source_branch": self.source_branch,
            "workspace_path": self.workspace_path,
            "git_initialized": self.git_initialized,
            "current_commit": self.current_commit,
            "status": self.status.value,
            "phase": self.phase.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "paused_at": self.paused_at.isoformat() if self.paused_at else None,
            "config": self.config,
        }


class BlockerSeverity(Enum):
    """Blocker severity for escalation (deprecated, use BlockerType)."""

    SYNC = "sync"  # Urgent, needs immediate response
    ASYNC = "async"  # Can wait, stack for later


class BlockerType(str, Enum):
    """Type of blocker requiring human intervention."""

    SYNC = "SYNC"  # Critical blocker - agent pauses immediately
    ASYNC = "ASYNC"  # Clarification request - agent continues work


class BlockerStatus(str, Enum):
    """Current status of a blocker."""

    PENDING = "PENDING"  # Awaiting user response
    RESOLVED = "RESOLVED"  # User has provided answer
    EXPIRED = "EXPIRED"  # Blocker timed out (24h default)


class ContextTier(Enum):
    """Virtual Project context tiers."""

    HOT = "hot"  # Always loaded, ~20K tokens
    WARM = "warm"  # On-demand, ~40K tokens
    COLD = "cold"  # Archived, queryable


class Severity(str, Enum):
    """Code review finding severity levels (Sprint 10)."""

    CRITICAL = "critical"  # Must fix before completion
    HIGH = "high"  # Should fix before completion
    MEDIUM = "medium"  # Should fix eventually
    LOW = "low"  # Nice to fix
    INFO = "info"  # Informational only


class ReviewCategory(str, Enum):
    """Code review finding categories (Sprint 10)."""

    SECURITY = "security"  # Security vulnerabilities
    PERFORMANCE = "performance"  # Performance issues
    QUALITY = "quality"  # Code quality problems
    MAINTAINABILITY = "maintainability"  # Hard to maintain code
    STYLE = "style"  # Style/formatting issues


class QualityGateType(str, Enum):
    """Types of quality gates (Sprint 10)."""

    TESTS = "tests"
    TYPE_CHECK = "type_check"
    COVERAGE = "coverage"
    CODE_REVIEW = "code_review"
    LINTING = "linting"
    SKIP_DETECTION = "skip_detection"


class CallType(str, Enum):
    """Type of LLM call for categorization (Sprint 10)."""

    TASK_EXECUTION = "task_execution"
    CODE_REVIEW = "code_review"
    COORDINATION = "coordination"
    OTHER = "other"


@dataclass
class Issue:
    """Represents a high-level work item that contains multiple tasks.

    Issues are numbered hierarchically (e.g., "1.5", "2.3") and can parallelize
    with other issues at the same level. Each issue contains sequential tasks.
    """

    id: Optional[int] = None
    project_id: Optional[int] = None
    issue_number: str = ""  # e.g., "1.5" or "2.1"
    title: str = ""
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 2  # 0-4, 0 = highest
    workflow_step: int = 1
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert Issue to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "issue_number": self.issue_number,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority,
            "workflow_step": self.workflow_step,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass
class IssueWithTaskCount:
    """Issue with associated task count for summary views.

    Uses composition to wrap an Issue and add task_count, reducing
    field duplication and ensuring changes to Issue are automatically
    reflected here.

    Used by get_issue_with_task_counts() to return typed results
    instead of raw dictionaries.
    """

    issue: Issue
    task_count: int = 0

    # Convenience accessors for common Issue fields
    @property
    def id(self) -> Optional[int]:
        return self.issue.id

    @property
    def project_id(self) -> Optional[int]:
        return self.issue.project_id

    @property
    def issue_number(self) -> str:
        return self.issue.issue_number

    @property
    def title(self) -> str:
        return self.issue.title

    @property
    def status(self) -> TaskStatus:
        return self.issue.status

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = self.issue.to_dict()
        result["task_count"] = self.task_count
        return result


@dataclass
class Task:
    """Represents an atomic development task within an issue.

    Tasks are numbered hierarchically (e.g., "1.5.1", "1.5.2") and are
    always sequential within their parent issue (cannot parallelize).
    Each task depends on the previous task in the sequence.
    """

    id: Optional[int] = None
    project_id: Optional[int] = None
    issue_id: Optional[int] = None  # Foreign key to parent issue
    task_number: str = ""  # e.g., "1.5.3"
    parent_issue_number: str = ""  # e.g., "1.5"
    title: str = ""
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    assigned_to: Optional[str] = None
    depends_on: str = ""  # Previous task number (e.g., "1.5.2")
    can_parallelize: bool = False  # Always FALSE within issue
    priority: int = 2  # 0-4, 0 = highest (inherited from issue)
    workflow_step: int = 1  # Maps to 15-step workflow
    requires_mcp: bool = False
    estimated_tokens: int = 0
    actual_tokens: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert Task to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "issue_id": self.issue_id,
            "task_number": self.task_number,
            "parent_issue_number": self.parent_issue_number,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "assigned_to": self.assigned_to,
            "depends_on": self.depends_on,
            "can_parallelize": self.can_parallelize,
            "priority": self.priority,
            "workflow_step": self.workflow_step,
            "requires_mcp": self.requires_mcp,
            "estimated_tokens": self.estimated_tokens,
            "actual_tokens": self.actual_tokens,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass
class Blocker:
    """Represents a task blocker requiring human input."""

    id: int
    task_id: int
    severity: BlockerSeverity
    reason: str
    question: str
    resolution: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None


@dataclass
class ContextItem:
    """Item in Virtual Project context system."""

    id: str
    project_id: int
    item_type: str  # 'current_task', 'active_file', 'recent_test', etc.
    content: str
    importance_score: float  # 0.0-1.0
    importance_reasoning: str
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    current_tier: ContextTier = ContextTier.WARM
    manual_pin: bool = False


@dataclass
class AgentMetrics:
    """Performance metrics for agent maturity assessment."""

    task_success_rate: float
    blocker_frequency: float
    test_pass_rate: float
    rework_rate: float
    context_efficiency: float  # tokens per task


@dataclass
class StateCheckpoint:
    """Legacy state snapshot for recovery (deprecated - use Checkpoint Pydantic model instead)."""

    id: str
    project_id: int
    trigger: str  # 'manual', 'auto', 'phase_transition', 'pause'
    state_snapshot: Dict[str, Any]
    git_commit: str
    db_backup_path: str
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Notification:
    """Multi-channel notification."""

    id: str
    project_id: int
    severity: BlockerSeverity
    title: str
    message: str
    blocker_id: Optional[int] = None
    action_required: str = ""
    channels: List[str] = field(default_factory=list)
    sent_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None


# Pydantic models for API validation and serialization


class BlockerModel(BaseModel):
    """Pydantic model for blocker database records."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: int
    agent_id: str
    task_id: Optional[int] = None
    blocker_type: BlockerType
    question: str = Field(..., max_length=2000)
    answer: Optional[str] = Field(None, max_length=5000)
    status: BlockerStatus
    created_at: datetime
    resolved_at: Optional[datetime] = None


class BlockerCreate(BaseModel):
    """Request model for creating a blocker."""

    agent_id: str
    task_id: Optional[int] = None
    blocker_type: BlockerType = BlockerType.ASYNC
    question: str = Field(..., min_length=1, max_length=2000)


class BlockerResolve(BaseModel):
    """Request model for resolving a blocker."""

    answer: str = Field(..., min_length=1, max_length=5000)

    @field_validator("answer")
    @classmethod
    def validate_answer_not_whitespace(cls, v: str) -> str:
        """Validate that answer is not empty or whitespace-only."""
        if not v.strip():
            raise ValueError("Answer cannot be empty or whitespace-only")
        return v


class BlockerListResponse(BaseModel):
    """Response model for listing blockers."""

    blockers: List[BlockerModel]
    total: int
    pending_count: int
    sync_count: int
    async_count: int = 0


# Context Management Models (007-context-management)


class ContextItemType(str, Enum):
    """Type of context item stored in the Virtual Project system."""

    TASK = "TASK"
    CODE = "CODE"
    ERROR = "ERROR"
    TEST_RESULT = "TEST_RESULT"
    PRD_SECTION = "PRD_SECTION"


class ContextItemModel(BaseModel):
    """Pydantic model for context item database records."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: str
    item_type: ContextItemType
    content: str
    importance_score: float = Field(..., ge=0.0, le=1.0)
    tier: str  # References ContextTier enum (HOT/WARM/COLD)
    access_count: int = 0
    created_at: datetime
    last_accessed: datetime


class ContextItemCreateModel(BaseModel):
    """Request model for creating a context item."""

    item_type: ContextItemType
    content: str = Field(..., min_length=1, max_length=100000)

    def validate_content(self) -> str:
        """Validate content is not empty or whitespace-only."""
        if not self.content.strip():
            raise ValueError("Content cannot be empty or whitespace-only")
        return self.content.strip()


class ContextItemResponse(BaseModel):
    """Response model for a single context item."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: str
    item_type: str
    content: str
    importance_score: float
    tier: str
    access_count: int
    created_at: datetime
    last_accessed: datetime


class ContextStats(BaseModel):
    """Response model for context statistics."""

    agent_id: str
    total_items: int
    hot_count: int
    warm_count: int
    cold_count: int
    total_tokens: int
    hot_tokens: int
    warm_tokens: int
    cold_tokens: int
    last_updated: datetime


class FlashSaveRequest(BaseModel):
    """Request model for initiating flash save."""

    force: bool = False  # Force flash save even if below 80% threshold


class FlashSaveResponse(BaseModel):
    """Response model for flash save operation."""

    checkpoint_id: int
    agent_id: str
    items_count: int
    items_archived: int
    hot_items_retained: int
    token_count_before: int
    token_count_after: int
    reduction_percentage: float
    created_at: datetime


# WebSocket Event Models (007-context-management)


class ContextTierUpdated(BaseModel):
    """WebSocket event when context tiers are updated.

    Emitted when the context tier algorithm redistributes items across
    HOT/WARM/COLD tiers based on importance scores, access patterns, and
    manual pins. This allows real-time monitoring of context evolution.

    Attributes:
        event_type: Always "context_tier_updated" for this event.
        agent_id: ID of the agent whose context was updated.
        item_count: Total number of context items after update.
        tier_changes: Count of items in each tier after redistribution.
        timestamp: UTC timestamp when tier update completed.

    Example WebSocket message:
        {
            "event_type": "context_tier_updated",
            "agent_id": "agent-123",
            "item_count": 30,
            "tier_changes": {"hot": 5, "warm": 10, "cold": 15},
            "timestamp": "2025-01-14T10:30:00Z"
        }
    """

    event_type: str = "context_tier_updated"
    agent_id: str
    item_count: int
    tier_changes: Dict[str, int]  # {"hot": 5, "warm": 10, "cold": 15}
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


class FlashSaveCompleted(BaseModel):
    """WebSocket event when flash save completes.

    Emitted when a flash save operation successfully creates a checkpoint
    and archives WARM/COLD context items. This event provides metrics on
    context reduction effectiveness.

    Attributes:
        event_type: Always "flash_save_completed" for this event.
        agent_id: ID of the agent whose context was flash-saved.
        checkpoint_id: Database ID of the created checkpoint record.
        reduction_percentage: Percentage reduction in token count (0-100).
        items_archived: Number of context items moved to checkpoint.
        timestamp: UTC timestamp when flash save completed.

    Example WebSocket message:
        {
            "event_type": "flash_save_completed",
            "agent_id": "agent-123",
            "checkpoint_id": 42,
            "reduction_percentage": 65.5,
            "items_archived": 25,
            "timestamp": "2025-01-14T10:35:00Z"
        }
    """

    event_type: str = "flash_save_completed"
    agent_id: str
    checkpoint_id: int
    reduction_percentage: float
    items_archived: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


# Sprint 9: MVP Completion Models


class LintResult(BaseModel):
    """Lint execution result.

    Stores results from linting tools (ruff, eslint) for tracking quality trends
    over time and enforcing quality gates.

    Attributes:
        id: Database ID (auto-generated)
        task_id: Task that was linted
        linter: Tool used (ruff, eslint, other)
        error_count: Number of critical errors (block task completion)
        warning_count: Number of non-blocking warnings
        files_linted: Number of files checked
        output: Full lint output (JSON or text)
        created_at: When lint was executed
    """

    id: Optional[int] = None
    task_id: Optional[int] = Field(None, description="Task ID (optional for in-memory results)")
    linter: Literal["ruff", "eslint", "other"] = Field(..., description="Linter tool")
    error_count: int = Field(0, ge=0, description="Number of errors")
    warning_count: int = Field(0, ge=0, description="Number of warnings")
    files_linted: int = Field(0, ge=0, description="Number of files checked")
    output: Optional[str] = Field(None, description="Full lint output (JSON or text)")
    created_at: Optional[datetime] = None

    @property
    def has_critical_errors(self) -> bool:
        """Check if lint found critical errors that block task."""
        return self.error_count > 0

    @property
    def total_issues(self) -> int:
        """Total issues (errors + warnings)."""
        return self.error_count + self.warning_count

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "task_id": self.task_id,
            "linter": self.linter,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "files_linted": self.files_linted,
            "output": self.output,
        }


class ReviewFinding(BaseModel):
    """Individual review finding.

    Represents a single code quality issue found during code review
    (complexity, security, style, or duplication).

    Attributes:
        category: Type of issue (complexity, security, style, duplication)
        severity: Criticality level (critical, high, medium, low)
        file_path: File containing the issue
        line_number: Line number (optional)
        message: Human-readable description
        suggestion: Recommended fix (optional)
        tool: Tool that detected issue (radon, bandit, etc.)
    """

    category: Literal["complexity", "security", "style", "duplication"] = Field(
        ..., description="Finding category"
    )
    severity: Literal["critical", "high", "medium", "low"] = Field(
        ..., description="Severity level"
    )
    file_path: str = Field(..., description="File with issue")
    line_number: Optional[int] = Field(None, description="Line number (if applicable)")
    message: str = Field(..., description="Human-readable description")
    suggestion: Optional[str] = Field(None, description="Recommended fix")
    tool: str = Field(..., description="Tool that detected issue (radon, bandit, etc.)")

    def to_markdown(self) -> str:
        """Format finding as markdown for blocker display."""
        severity_emoji = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "⚪",
        }

        location = f"{self.file_path}:{self.line_number}" if self.line_number else self.file_path

        md = f"{severity_emoji[self.severity]} **{self.severity.upper()}** [{self.category}] {location}\n"
        md += f"   {self.message}\n"

        if self.suggestion:
            md += f"   💡 Suggestion: {self.suggestion}\n"

        return md


class ReviewReport(BaseModel):
    """Complete review report for a task.

    Aggregates all review findings into a comprehensive quality assessment
    with scoring and approve/reject decision.

    Attributes:
        task_id: Task that was reviewed
        reviewer_agent_id: Agent that performed review
        overall_score: Overall quality score (0-100)
        complexity_score: Complexity subscore (0-100)
        security_score: Security subscore (0-100)
        style_score: Style subscore (0-100)
        status: Review decision (approved, changes_requested, rejected)
        findings: List of individual findings
        summary: Human-readable summary
    """

    task_id: int
    reviewer_agent_id: str
    overall_score: float = Field(..., ge=0, le=100, description="Overall quality score (0-100)")
    complexity_score: float = Field(..., ge=0, le=100)
    security_score: float = Field(..., ge=0, le=100)
    style_score: float = Field(..., ge=0, le=100)
    status: Literal["approved", "changes_requested", "rejected"]
    findings: List[ReviewFinding] = Field(default_factory=list)
    summary: str = Field(..., description="Human-readable summary")

    @property
    def has_critical_findings(self) -> bool:
        """Check if any findings are critical severity."""
        return any(f.severity == "critical" for f in self.findings)

    @property
    def critical_count(self) -> int:
        """Count critical findings."""
        return sum(1 for f in self.findings if f.severity == "critical")

    @property
    def high_count(self) -> int:
        """Count high severity findings."""
        return sum(1 for f in self.findings if f.severity == "high")

    def to_blocker_message(self) -> str:
        """Format review report as blocker message."""
        msg = f"## Code Review: {self.status.replace('_', ' ').title()}\n\n"
        msg += f"**Overall Score**: {self.overall_score:.1f}/100\n\n"

        if self.findings:
            msg += f"**Findings**: {len(self.findings)} issues ({self.critical_count} critical, {self.high_count} high)\n\n"

            # Group by severity
            for severity in ["critical", "high", "medium", "low"]:
                severity_findings = [f for f in self.findings if f.severity == severity]
                if severity_findings:
                    msg += f"### {severity.upper()} Issues\n\n"
                    for finding in severity_findings:
                        msg += finding.to_markdown() + "\n"

        msg += f"\n---\n\n{self.summary}"

        return msg


# ============================================================================
# Discovery Answer UI Models (Feature: 012-discovery-answer-ui)
# ============================================================================


class DiscoveryAnswer(BaseModel):
    """Request model for discovery answer submission."""

    model_config = ConfigDict(str_strip_whitespace=True)

    answer: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="User's answer to the current discovery question",
    )

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, v: str) -> str:
        """Ensure answer is not empty after trimming."""
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Answer cannot be empty or whitespace only")
        if len(trimmed) > 5000:
            raise ValueError("Answer cannot exceed 5000 characters")
        return trimmed


class DiscoveryAnswerResponse(BaseModel):
    """Response model for discovery answer submission."""

    success: bool = Field(..., description="Whether the answer was successfully processed")

    next_question: Optional[str] = Field(
        None, description="Next discovery question text (null if discovery complete)"
    )

    is_complete: bool = Field(..., description="Whether the discovery phase is complete")

    current_index: int = Field(..., ge=0, description="Current question index (0-based)")

    total_questions: int = Field(..., gt=0, description="Total number of discovery questions")

    progress_percentage: float = Field(
        ..., ge=0.0, le=100.0, description="Discovery completion percentage (0.0 - 100.0)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "next_question": "What tech stack are you planning to use?",
                "is_complete": False,
                "current_index": 3,
                "total_questions": 20,
                "progress_percentage": 15.0,
            }
        }
    )


# ============================================================================
# Sprint 10 Models (Feature: 015-review-polish)
# ============================================================================


class CodeReview(BaseModel):
    """Code review finding from Review Agent (Sprint 10)."""

    id: Optional[int] = None
    task_id: int
    agent_id: str
    project_id: int
    file_path: str = Field(..., description="Relative path from project root")
    line_number: Optional[int] = Field(None, description="Line number, None for file-level")
    severity: Severity
    category: ReviewCategory
    message: str = Field(..., min_length=10, description="Description of the issue")
    recommendation: Optional[str] = Field(None, description="How to fix it")
    code_snippet: Optional[str] = Field(None, description="Offending code for context")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(use_enum_values=True)

    @property
    def is_blocking(self) -> bool:
        """Whether this finding should block task completion."""
        # Handle both enum and string values (use_enum_values=True converts to strings)
        blocking_severities = [Severity.CRITICAL.value, Severity.HIGH.value]
        severity_value = self.severity if isinstance(self.severity, str) else self.severity.value
        return severity_value in blocking_severities


class TokenUsage(BaseModel):
    """Token usage record for a single LLM call (Sprint 10)."""

    id: Optional[int] = None
    task_id: Optional[int] = None  # None for non-task calls
    agent_id: str
    project_id: int
    model_name: str = Field(..., description="e.g., claude-sonnet-4-5")
    input_tokens: int = Field(..., ge=0)
    output_tokens: int = Field(..., ge=0)
    estimated_cost_usd: float = Field(..., ge=0.0)
    actual_cost_usd: Optional[float] = Field(None, ge=0.0)
    call_type: CallType = CallType.OTHER
    session_id: Optional[str] = Field(None, description="SDK session ID for conversation tracking")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(use_enum_values=True)

    @property
    def total_tokens(self) -> int:
        """Total tokens (input + output)."""
        return self.input_tokens + self.output_tokens

    @staticmethod
    def calculate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate estimated cost in USD.

        Pricing as of 2025-11:
        - Claude Sonnet 4.5: $3.00 input / $15.00 output per MTok
        - Claude Opus 4: $15.00 input / $75.00 output per MTok
        - Claude Haiku 4: $0.80 input / $4.00 output per MTok
        """
        pricing = {
            "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
            "claude-opus-4": {"input": 15.00, "output": 75.00},
            "claude-haiku-4": {"input": 0.80, "output": 4.00},
        }

        if model_name not in pricing:
            raise ValueError(f"Unknown model: {model_name}")

        prices = pricing[model_name]
        cost = (input_tokens * prices["input"] / 1_000_000) + (
            output_tokens * prices["output"] / 1_000_000
        )
        return round(cost, 6)  # 6 decimal places for precision


class QualityGateFailure(BaseModel):
    """Individual quality gate failure (Sprint 10)."""

    gate: QualityGateType
    reason: str = Field(..., min_length=5)
    details: Optional[str] = None  # Full error output
    severity: Severity = Severity.HIGH


class QualityGateResult(BaseModel):
    """Result of running quality gates for a task (Sprint 10)."""

    task_id: int
    status: str = Field(..., description="passed or failed")
    failures: List[QualityGateFailure] = Field(default_factory=list)
    execution_time_seconds: float = Field(..., ge=0.0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def passed(self) -> bool:
        """Whether all gates passed."""
        return self.status == "passed" and len(self.failures) == 0

    @property
    def has_critical_failures(self) -> bool:
        """Whether any failures are critical."""
        return any(f.severity == Severity.CRITICAL for f in self.failures)


class CheckpointMetadata(BaseModel):
    """Metadata stored in checkpoint for quick inspection (Sprint 10)."""

    project_id: int
    phase: str  # discovery, planning, active, review, complete
    tasks_completed: int
    tasks_total: int
    agents_active: List[str]
    last_task_completed: Optional[str] = None
    context_items_count: int
    total_cost_usd: float


class Checkpoint(BaseModel):
    """Project checkpoint for restore operations (Sprint 10)."""

    id: Optional[int] = None
    project_id: int
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    trigger: str = Field(..., description="manual, auto, phase_transition, pause")
    git_commit: str = Field(..., min_length=7, max_length=40, description="Git commit SHA")
    database_backup_path: str = Field(..., description="Path to .sqlite backup")
    context_snapshot_path: str = Field(..., description="Path to context JSON")
    metadata: CheckpointMetadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def validate_files_exist(self) -> bool:
        """Check if all checkpoint files exist."""
        from pathlib import Path

        db_path = Path(self.database_backup_path)
        context_path = Path(self.context_snapshot_path)
        return db_path.exists() and context_path.exists()
