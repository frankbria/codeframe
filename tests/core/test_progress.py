"""Tests for BatchProgress tracking."""

from datetime import datetime, timezone, timedelta

from codeframe.core.progress import BatchProgress


class TestBatchProgressBasic:
    """Test basic BatchProgress functionality."""

    def test_initial_state(self):
        """Should initialize with correct defaults."""
        progress = BatchProgress(total_tasks=5)

        assert progress.total_tasks == 5
        assert progress.completed_tasks == 0
        assert progress.failed_tasks == 0
        assert progress.blocked_tasks == 0
        assert progress.processed_tasks == 0
        assert progress.remaining_tasks == 5
        assert progress.running_tasks == 0

    def test_progress_percent_empty(self):
        """Should show 0% when no tasks processed."""
        progress = BatchProgress(total_tasks=10)
        assert progress.progress_percent == 0.0

    def test_progress_percent_partial(self):
        """Should calculate correct percentage."""
        progress = BatchProgress(
            total_tasks=10,
            completed_tasks=3,
            failed_tasks=2,
        )
        assert progress.progress_percent == 50.0

    def test_progress_percent_complete(self):
        """Should show 100% when all tasks processed."""
        progress = BatchProgress(
            total_tasks=5,
            completed_tasks=4,
            failed_tasks=1,
        )
        assert progress.progress_percent == 100.0

    def test_progress_percent_zero_tasks(self):
        """Should handle zero total tasks."""
        progress = BatchProgress(total_tasks=0)
        assert progress.progress_percent == 100.0


class TestTaskRecording:
    """Test task start/complete recording."""

    def test_record_task_start(self):
        """Should track task start times."""
        progress = BatchProgress(total_tasks=3)
        progress.record_task_start("task-1")

        assert "task-1" in progress.task_start_times
        assert progress.running_tasks == 1

    def test_record_task_complete(self):
        """Should track completion and calculate duration."""
        progress = BatchProgress(total_tasks=3)
        progress.record_task_start("task-1")
        progress.record_task_complete("task-1")

        assert progress.completed_tasks == 1
        assert "task-1" not in progress.task_start_times
        assert len(progress.task_durations) == 1
        assert progress.running_tasks == 0

    def test_record_task_complete_without_start(self):
        """Should handle completion without recorded start."""
        progress = BatchProgress(total_tasks=3)
        progress.record_task_complete("task-1")

        assert progress.completed_tasks == 1
        assert len(progress.task_durations) == 0  # No duration calculated

    def test_record_task_failed(self):
        """Should track failures and remove from running."""
        progress = BatchProgress(total_tasks=3)
        progress.record_task_start("task-1")
        progress.record_task_failed("task-1")

        assert progress.failed_tasks == 1
        assert progress.running_tasks == 0
        assert "task-1" not in progress.task_start_times

    def test_record_task_blocked(self):
        """Should track blocked tasks."""
        progress = BatchProgress(total_tasks=3)
        progress.record_task_start("task-1")
        progress.record_task_blocked("task-1")

        assert progress.blocked_tasks == 1
        assert progress.running_tasks == 0


class TestETACalculation:
    """Test ETA estimation."""

    def test_eta_no_data(self):
        """Should return None when no duration data."""
        progress = BatchProgress(total_tasks=5)
        assert progress.eta_seconds is None
        assert progress.average_task_duration is None

    def test_eta_with_durations(self):
        """Should calculate ETA based on average duration."""
        progress = BatchProgress(total_tasks=5, completed_tasks=2)
        progress.task_durations = [10.0, 20.0]  # Average: 15s

        assert progress.average_task_duration == 15.0
        assert progress.remaining_tasks == 3
        assert progress.eta_seconds == 45.0  # 3 tasks * 15s

    def test_eta_all_complete(self):
        """Should return None when no remaining tasks."""
        progress = BatchProgress(total_tasks=2, completed_tasks=2)
        progress.task_durations = [10.0, 20.0]

        assert progress.eta_seconds is None

    def test_format_eta_calculating(self):
        """Should show calculating when no data."""
        progress = BatchProgress(total_tasks=5)
        assert progress.format_eta() == "calculating..."

    def test_format_eta_complete(self):
        """Should show complete when done."""
        progress = BatchProgress(total_tasks=2, completed_tasks=2)
        assert progress.format_eta() == "complete"

    def test_format_eta_seconds(self):
        """Should format small ETAs in seconds."""
        progress = BatchProgress(total_tasks=5, completed_tasks=4)
        progress.task_durations = [30.0]  # 1 remaining * 30s

        assert progress.format_eta() == "30s"

    def test_format_eta_minutes(self):
        """Should format ETAs in minutes and seconds."""
        progress = BatchProgress(total_tasks=10, completed_tasks=5)
        progress.task_durations = [30.0]  # 5 remaining * 30s = 150s = 2m 30s

        assert progress.format_eta() == "2m 30s"

    def test_format_eta_hours(self):
        """Should format large ETAs in hours."""
        progress = BatchProgress(total_tasks=100, completed_tasks=10)
        progress.task_durations = [60.0]  # 90 remaining * 60s = 5400s = 1h 30m

        assert progress.format_eta() == "1h 30m"


class TestElapsedTime:
    """Test elapsed time tracking."""

    def test_elapsed_seconds(self):
        """Should calculate elapsed time."""
        start = datetime.now(timezone.utc) - timedelta(seconds=120)
        progress = BatchProgress(total_tasks=5, started_at=start)

        # Allow some tolerance for test execution time
        assert 119 <= progress.elapsed_seconds <= 121

    def test_format_elapsed_seconds(self):
        """Should format small elapsed times."""
        start = datetime.now(timezone.utc) - timedelta(seconds=45)
        progress = BatchProgress(total_tasks=5, started_at=start)

        result = progress.format_elapsed()
        assert result == "45s" or result == "44s" or result == "46s"

    def test_format_elapsed_minutes(self):
        """Should format elapsed time in minutes."""
        start = datetime.now(timezone.utc) - timedelta(seconds=150)
        progress = BatchProgress(total_tasks=5, started_at=start)

        result = progress.format_elapsed()
        assert "2m" in result and "s" in result

    def test_format_elapsed_hours(self):
        """Should format elapsed time in hours."""
        start = datetime.now(timezone.utc) - timedelta(hours=1, minutes=30)
        progress = BatchProgress(total_tasks=5, started_at=start)

        result = progress.format_elapsed()
        assert "1h" in result and "30m" in result


class TestStatusSummary:
    """Test status summary generation."""

    def test_summary_starting(self):
        """Should show pending when tasks waiting."""
        progress = BatchProgress(total_tasks=5)
        assert progress.status_summary() == "5 pending"

    def test_summary_empty_batch(self):
        """Should show starting when no tasks at all."""
        progress = BatchProgress(total_tasks=0)
        assert progress.status_summary() == "starting..."

    def test_summary_running(self):
        """Should show running tasks."""
        progress = BatchProgress(total_tasks=5)
        progress.record_task_start("task-1")

        assert "1 running" in progress.status_summary()

    def test_summary_mixed(self):
        """Should show all status counts."""
        progress = BatchProgress(
            total_tasks=10,
            completed_tasks=3,
            failed_tasks=1,
            blocked_tasks=1,
        )
        progress.record_task_start("task-6")

        summary = progress.status_summary()
        assert "3 completed" in summary
        assert "1 failed" in summary
        assert "1 blocked" in summary
        assert "1 running" in summary
        assert "4 pending" in summary  # 10 - 3 - 1 - 1 - 1 running = 4

    def test_summary_all_complete(self):
        """Should show only completed when done."""
        progress = BatchProgress(total_tasks=3, completed_tasks=3)

        summary = progress.status_summary()
        assert "3 completed" in summary
        assert "pending" not in summary
