"""Progress tracking for batch execution.

Provides ETA estimation based on completed task durations.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class BatchProgress:
    """Tracks batch execution progress for ETA calculation."""

    total_tasks: int
    completed_tasks: int = 0
    failed_tasks: int = 0
    blocked_tasks: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    task_durations: list[float] = field(default_factory=list)
    task_start_times: dict[str, datetime] = field(default_factory=dict)

    @property
    def processed_tasks(self) -> int:
        """Tasks that are no longer pending."""
        return self.completed_tasks + self.failed_tasks + self.blocked_tasks

    @property
    def remaining_tasks(self) -> int:
        """Tasks still to be processed."""
        return max(0, self.total_tasks - self.processed_tasks)

    @property
    def running_tasks(self) -> int:
        """Tasks currently in progress."""
        return len(self.task_start_times)

    @property
    def average_task_duration(self) -> Optional[float]:
        """Average seconds per completed task."""
        if not self.task_durations:
            return None
        return sum(self.task_durations) / len(self.task_durations)

    @property
    def eta_seconds(self) -> Optional[float]:
        """Estimated seconds to completion."""
        avg = self.average_task_duration
        if avg is None or self.remaining_tasks == 0:
            return None
        return avg * self.remaining_tasks

    def format_eta(self) -> str:
        """Human-readable ETA string."""
        eta = self.eta_seconds
        if eta is None:
            if self.remaining_tasks == 0:
                return "complete"
            return "calculating..."
        hours, remainder = divmod(int(eta), 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}h {minutes}m"
        if minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    @property
    def progress_percent(self) -> float:
        """Completion percentage (0-100)."""
        if self.total_tasks == 0:
            return 100.0
        return (self.processed_tasks / self.total_tasks) * 100

    @property
    def elapsed_seconds(self) -> float:
        """Seconds since batch started."""
        return (datetime.now(timezone.utc) - self.started_at).total_seconds()

    def format_elapsed(self) -> str:
        """Human-readable elapsed time."""
        elapsed = int(self.elapsed_seconds)
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        if minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    def record_task_start(self, task_id: str) -> None:
        """Record when a task starts for duration tracking."""
        self.task_start_times[task_id] = datetime.now(timezone.utc)

    def record_task_complete(self, task_id: str) -> None:
        """Record task completion and calculate duration."""
        self.completed_tasks += 1
        start_time = self.task_start_times.pop(task_id, None)
        if start_time:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.task_durations.append(duration)

    def record_task_failed(self, task_id: str) -> None:
        """Record task failure."""
        self.failed_tasks += 1
        self.task_start_times.pop(task_id, None)

    def record_task_blocked(self, task_id: str) -> None:
        """Record task blocked."""
        self.blocked_tasks += 1
        self.task_start_times.pop(task_id, None)

    def status_summary(self) -> str:
        """One-line status summary."""
        parts = []
        if self.completed_tasks:
            parts.append(f"{self.completed_tasks} completed")
        if self.failed_tasks:
            parts.append(f"{self.failed_tasks} failed")
        if self.blocked_tasks:
            parts.append(f"{self.blocked_tasks} blocked")
        if self.running_tasks:
            parts.append(f"{self.running_tasks} running")
        if self.remaining_tasks - self.running_tasks > 0:
            parts.append(f"{self.remaining_tasks - self.running_tasks} pending")
        return " | ".join(parts) if parts else "starting..."
