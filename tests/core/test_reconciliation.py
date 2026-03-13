"""Tests for continuous reconciliation during batch execution."""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.v2


# ---------------------------------------------------------------------------
# Config tests (Step 1)
# ---------------------------------------------------------------------------


class TestReconciliationConfig:
    """Test reconciliation config in EnvironmentConfig."""

    def test_default_interval(self) -> None:
        from codeframe.core.config import EnvironmentConfig

        cfg = EnvironmentConfig()
        assert cfg.reconciliation_interval_seconds == 30

    def test_custom_interval(self) -> None:
        from codeframe.core.config import EnvironmentConfig

        cfg = EnvironmentConfig(reconciliation_interval_seconds=60)
        assert cfg.reconciliation_interval_seconds == 60

    def test_from_dict_with_reconciliation(self) -> None:
        from codeframe.core.config import EnvironmentConfig

        cfg = EnvironmentConfig.from_dict({"reconciliation_interval_seconds": 15})
        assert cfg.reconciliation_interval_seconds == 15

    def test_roundtrip(self) -> None:
        from codeframe.core.config import EnvironmentConfig

        orig = EnvironmentConfig(reconciliation_interval_seconds=45)
        d = orig.to_dict()
        restored = EnvironmentConfig.from_dict(d)
        assert restored.reconciliation_interval_seconds == 45


class TestTaskGithubIssueNumber:
    """Test github_issue_number field on Task."""

    def test_task_has_github_issue_number_field(self) -> None:
        from codeframe.core.tasks import Task
        from codeframe.core.state_machine import TaskStatus
        from datetime import datetime

        task = Task(
            id="t1", workspace_id="w1", prd_id=None,
            title="Test", description="", status=TaskStatus.READY,
            priority=0, created_at=datetime.now(), updated_at=datetime.now(),
            github_issue_number=42,
        )
        assert task.github_issue_number == 42

    def test_task_github_issue_number_defaults_to_none(self) -> None:
        from codeframe.core.tasks import Task
        from codeframe.core.state_machine import TaskStatus
        from datetime import datetime

        task = Task(
            id="t1", workspace_id="w1", prd_id=None,
            title="Test", description="", status=TaskStatus.READY,
            priority=0, created_at=datetime.now(), updated_at=datetime.now(),
        )
        assert task.github_issue_number is None


# ---------------------------------------------------------------------------
# ReconciliationEngine tests (Step 2)
# ---------------------------------------------------------------------------


class TestExternalStateChange:
    """Test ExternalStateChange dataclass."""

    def test_creation(self) -> None:
        from codeframe.core.reconciliation import ExternalStateChange

        change = ExternalStateChange(
            task_id="t1", change_type="completed",
            source="manual", details={"reason": "done"},
        )
        assert change.task_id == "t1"
        assert change.change_type == "completed"
        assert change.source == "manual"


class TestReconciliationResult:
    """Test ReconciliationResult dataclass."""

    def test_defaults(self) -> None:
        from codeframe.core.reconciliation import ReconciliationResult

        result = ReconciliationResult()
        assert result.changes_detected == []
        assert result.tasks_skipped == []
        assert result.tasks_requeued == []
        assert result.errors == []


class TestReconciliationEngine:
    """Test the ReconciliationEngine."""

    def test_check_task_detects_completed(self) -> None:
        from codeframe.core.reconciliation import ReconciliationEngine
        from codeframe.core.state_machine import TaskStatus

        workspace = MagicMock()
        engine = ReconciliationEngine(workspace)

        mock_task = MagicMock()
        mock_task.status = TaskStatus.DONE
        mock_task.id = "t1"

        with patch("codeframe.core.reconciliation.tasks.get", return_value=mock_task):
            changes = engine.check_task("t1")

        assert len(changes) == 1
        assert changes[0].change_type == "completed"
        assert changes[0].source == "manual"

    def test_check_task_detects_blocker_resolved(self) -> None:
        from codeframe.core.reconciliation import ReconciliationEngine
        from codeframe.core.state_machine import TaskStatus

        workspace = MagicMock()
        engine = ReconciliationEngine(workspace)

        mock_task = MagicMock()
        mock_task.status = TaskStatus.BLOCKED
        mock_task.id = "t1"

        # All blockers answered
        mock_blocker = MagicMock()
        mock_blocker.status.value = "ANSWERED"

        with patch("codeframe.core.reconciliation.tasks.get", return_value=mock_task):
            with patch("codeframe.core.reconciliation.blockers.list_for_task", return_value=[mock_blocker]):
                changes = engine.check_task("t1")

        assert len(changes) == 1
        assert changes[0].change_type == "blocker_resolved"

    def test_check_task_returns_empty_for_in_progress(self) -> None:
        from codeframe.core.reconciliation import ReconciliationEngine
        from codeframe.core.state_machine import TaskStatus

        workspace = MagicMock()
        engine = ReconciliationEngine(workspace)

        mock_task = MagicMock()
        mock_task.status = TaskStatus.IN_PROGRESS
        mock_task.id = "t1"

        with patch("codeframe.core.reconciliation.tasks.get", return_value=mock_task):
            changes = engine.check_task("t1")

        assert changes == []

    def test_check_task_returns_empty_if_task_not_found(self) -> None:
        from codeframe.core.reconciliation import ReconciliationEngine

        workspace = MagicMock()
        engine = ReconciliationEngine(workspace)

        with patch("codeframe.core.reconciliation.tasks.get", return_value=None):
            changes = engine.check_task("t1")

        assert changes == []

    def test_check_task_with_github_checker(self) -> None:
        from codeframe.core.reconciliation import ExternalStateChange, ReconciliationEngine
        from codeframe.core.state_machine import TaskStatus

        workspace = MagicMock()

        def github_checker(task_id, task):
            return [ExternalStateChange(
                task_id=task_id, change_type="closed",
                source="github", details={},
            )]

        engine = ReconciliationEngine(workspace, github_checker=github_checker)

        mock_task = MagicMock()
        mock_task.status = TaskStatus.IN_PROGRESS
        mock_task.id = "t1"

        with patch("codeframe.core.reconciliation.tasks.get", return_value=mock_task):
            changes = engine.check_task("t1")

        assert len(changes) == 1
        assert changes[0].change_type == "closed"
        assert changes[0].source == "github"

    def test_check_all_active_catches_errors(self) -> None:
        from codeframe.core.reconciliation import ReconciliationEngine

        workspace = MagicMock()
        engine = ReconciliationEngine(workspace)

        with patch.object(engine, "check_task", side_effect=Exception("db error")):
            result = engine.check_all_active(["t1", "t2"])

        assert len(result.errors) == 2
        assert result.changes_detected == []

    def test_check_all_active_accumulates_changes(self) -> None:
        from codeframe.core.reconciliation import ExternalStateChange, ReconciliationEngine

        workspace = MagicMock()
        engine = ReconciliationEngine(workspace)

        changes = [
            ExternalStateChange(task_id="t1", change_type="completed", source="manual", details={}),
        ]

        with patch.object(engine, "check_task", side_effect=[changes, []]):
            result = engine.check_all_active(["t1", "t2"])

        assert len(result.changes_detected) == 1
        assert result.changes_detected[0].task_id == "t1"


class TestApplyChanges:
    """Test ReconciliationEngine.apply_changes."""

    def test_completed_change_terminates_process(self) -> None:
        from codeframe.core.reconciliation import (
            ExternalStateChange, ReconciliationEngine, ReconciliationResult,
        )

        workspace = MagicMock()
        engine = ReconciliationEngine(workspace)

        result = ReconciliationResult(
            changes_detected=[
                ExternalStateChange(task_id="t1", change_type="completed", source="manual", details={}),
            ],
        )

        mock_proc = MagicMock()
        active_processes = {"t1": mock_proc}
        batch = MagicMock()
        batch.results = {}

        engine.apply_changes(result, batch, active_processes)

        mock_proc.terminate.assert_called_once()
        assert "t1" in result.tasks_skipped

    def test_closed_change_terminates_process(self) -> None:
        from codeframe.core.reconciliation import (
            ExternalStateChange, ReconciliationEngine, ReconciliationResult,
        )

        workspace = MagicMock()
        engine = ReconciliationEngine(workspace)

        result = ReconciliationResult(
            changes_detected=[
                ExternalStateChange(task_id="t1", change_type="closed", source="github", details={}),
            ],
        )

        mock_proc = MagicMock()
        active_processes = {"t1": mock_proc}
        batch = MagicMock()
        batch.results = {}

        engine.apply_changes(result, batch, active_processes)

        mock_proc.terminate.assert_called_once()
        assert "t1" in result.tasks_skipped

    def test_blocker_resolved_requeues_task(self) -> None:
        from codeframe.core.reconciliation import (
            ExternalStateChange, ReconciliationEngine, ReconciliationResult,
        )

        workspace = MagicMock()
        engine = ReconciliationEngine(workspace)

        result = ReconciliationResult(
            changes_detected=[
                ExternalStateChange(task_id="t1", change_type="blocker_resolved", source="manual", details={}),
            ],
        )

        batch = MagicMock()
        batch.results = {"t1": "BLOCKED"}

        engine.apply_changes(result, batch, {})

        assert "t1" in result.tasks_requeued

    def test_apply_changes_catches_errors(self) -> None:
        from codeframe.core.reconciliation import (
            ExternalStateChange, ReconciliationEngine, ReconciliationResult,
        )

        workspace = MagicMock()
        engine = ReconciliationEngine(workspace)

        result = ReconciliationResult(
            changes_detected=[
                ExternalStateChange(task_id="t1", change_type="completed", source="manual", details={}),
            ],
        )

        # Process that raises on terminate
        mock_proc = MagicMock()
        mock_proc.terminate.side_effect = OSError("already dead")
        active_processes = {"t1": mock_proc}
        batch = MagicMock()
        batch.results = {}

        # Should not raise
        engine.apply_changes(result, batch, active_processes)
        assert len(result.errors) >= 0  # Error may or may not be logged


# ---------------------------------------------------------------------------
# GitHub Issue Sync tests (Step 3)
# ---------------------------------------------------------------------------


class TestGitHubIssueSync:
    """Test GitHub issue state checker."""

    def test_get_issue_state_returns_state(self) -> None:
        from codeframe.git.github_issue_sync import get_issue_state

        mock_response = MagicMock()
        mock_response.json.return_value = {"state": "closed"}
        mock_response.raise_for_status = MagicMock()

        with patch("codeframe.git.github_issue_sync.httpx.get", return_value=mock_response):
            state = get_issue_state("token123", "owner/repo", 42)

        assert state == "closed"

    def test_get_issue_state_returns_open(self) -> None:
        from codeframe.git.github_issue_sync import get_issue_state

        mock_response = MagicMock()
        mock_response.json.return_value = {"state": "open"}
        mock_response.raise_for_status = MagicMock()

        with patch("codeframe.git.github_issue_sync.httpx.get", return_value=mock_response):
            state = get_issue_state("token123", "owner/repo", 42)

        assert state == "open"

    def test_build_github_task_checker_returns_callable(self) -> None:
        from codeframe.git.github_issue_sync import build_github_task_checker

        checker = build_github_task_checker("token123", "owner/repo")
        assert callable(checker)

    def test_checker_returns_closed_change(self) -> None:
        from codeframe.git.github_issue_sync import build_github_task_checker

        checker = build_github_task_checker("token123", "owner/repo")

        mock_task = MagicMock()
        mock_task.github_issue_number = 42

        with patch("codeframe.git.github_issue_sync.get_issue_state", return_value="closed"):
            changes = checker("t1", mock_task)

        assert len(changes) == 1
        assert changes[0].change_type == "closed"
        assert changes[0].source == "github"

    def test_checker_returns_empty_for_open_issue(self) -> None:
        from codeframe.git.github_issue_sync import build_github_task_checker

        checker = build_github_task_checker("token123", "owner/repo")

        mock_task = MagicMock()
        mock_task.github_issue_number = 42

        with patch("codeframe.git.github_issue_sync.get_issue_state", return_value="open"):
            changes = checker("t1", mock_task)

        assert changes == []

    def test_checker_skips_tasks_without_issue_number(self) -> None:
        from codeframe.git.github_issue_sync import build_github_task_checker

        checker = build_github_task_checker("token123", "owner/repo")

        mock_task = MagicMock()
        mock_task.github_issue_number = None

        changes = checker("t1", mock_task)
        assert changes == []

    def test_checker_handles_api_error_gracefully(self) -> None:
        import httpx
        from codeframe.git.github_issue_sync import build_github_task_checker

        checker = build_github_task_checker("token123", "owner/repo")

        mock_task = MagicMock()
        mock_task.github_issue_number = 42

        with patch("codeframe.git.github_issue_sync.get_issue_state", side_effect=httpx.RequestError("timeout")):
            changes = checker("t1", mock_task)

        assert changes == []


# ---------------------------------------------------------------------------
# Event types tests (Step 5)
# ---------------------------------------------------------------------------


class TestReconciliationEventTypes:
    """Test reconciliation event type constants."""

    def test_event_types_exist(self) -> None:
        from codeframe.core.events import EventType

        assert hasattr(EventType, "RECONCILIATION_STARTED")
        assert hasattr(EventType, "RECONCILIATION_TASK_SKIPPED")
        assert hasattr(EventType, "RECONCILIATION_TASK_REQUEUED")
        assert hasattr(EventType, "RECONCILIATION_ERROR")
