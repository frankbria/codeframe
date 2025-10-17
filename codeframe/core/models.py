"""Core data models for CodeFRAME."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any


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
    """Blocker severity for escalation."""
    SYNC = "sync"  # Urgent, needs immediate response
    ASYNC = "async"  # Can wait, stack for later


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