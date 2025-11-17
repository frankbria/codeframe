"""Core data models for CodeFRAME."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator


class TaskStatus(Enum):
    """Task execution status."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


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
    COMPLETED = "completed"


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
class Checkpoint:
    """State snapshot for recovery."""

    id: str
    project_id: int
    trigger: str  # 'manual', 'pre_compactification', 'task_complete'
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
