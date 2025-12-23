"""Domain-specific repository exports.

Extracted from monolithic Database class for better maintainability.
Each repository handles operations for a specific domain.
"""

from codeframe.persistence.repositories.base import BaseRepository
from codeframe.persistence.repositories.project_repository import ProjectRepository
from codeframe.persistence.repositories.issue_repository import IssueRepository
from codeframe.persistence.repositories.task_repository import TaskRepository
from codeframe.persistence.repositories.agent_repository import AgentRepository
from codeframe.persistence.repositories.blocker_repository import BlockerRepository
from codeframe.persistence.repositories.memory_repository import MemoryRepository
from codeframe.persistence.repositories.context_repository import ContextRepository
from codeframe.persistence.repositories.checkpoint_repository import CheckpointRepository
from codeframe.persistence.repositories.git_repository import GitRepository
from codeframe.persistence.repositories.test_repository import TestRepository
from codeframe.persistence.repositories.lint_repository import LintRepository
from codeframe.persistence.repositories.review_repository import ReviewRepository
from codeframe.persistence.repositories.quality_repository import QualityRepository
from codeframe.persistence.repositories.token_repository import TokenRepository
from codeframe.persistence.repositories.correction_repository import CorrectionRepository
from codeframe.persistence.repositories.activity_repository import ActivityRepository
from codeframe.persistence.repositories.audit_repository import AuditRepository

__all__ = [
    "BaseRepository",
    "ProjectRepository",
    "IssueRepository",
    "TaskRepository",
    "AgentRepository",
    "BlockerRepository",
    "MemoryRepository",
    "ContextRepository",
    "CheckpointRepository",
    "GitRepository",
    "TestRepository",
    "LintRepository",
    "ReviewRepository",
    "QualityRepository",
    "TokenRepository",
    "CorrectionRepository",
    "ActivityRepository",
    "AuditRepository",
]
