"""Integration tests for QualityTracker integration with WorkerAgent.

These tests verify the complete quality tracking workflow:
1. Quality metrics recorded after task completion
2. Degradation detected and blocker created
3. Context reset recommended when quality degrades
4. Checkpoint includes quality metrics
5. Dashboard displays quality trends
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, Mock, AsyncMock

from codeframe.agents.worker_agent import WorkerAgent
from codeframe.enforcement.quality_tracker import QualityTracker, QualityMetrics
from codeframe.lib.checkpoint_manager import CheckpointManager
from codeframe.persistence.database import Database
from codeframe.core.models import Task, TaskStatus, AgentMaturity


class TestQualityTrackerIntegration:
    """Integration tests for quality tracker workflow."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create temporary database."""
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        db.initialize()
        return db

    @pytest.fixture
    def project_root(self, tmp_path):
        """Create temporary project root with .codeframe directory."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Create .codeframe directory for quality history
        codeframe_dir = project_dir / ".codeframe"
        codeframe_dir.mkdir()

        # Create basic Python project structure
        (project_dir / "src").mkdir()
        (project_dir / "tests").mkdir()

        # Create pyproject.toml for language detection
        (project_dir / "pyproject.toml").write_text(
            """
[project]
name = "test-project"
version = "0.1.0"

[tool.pytest.ini_options]
testpaths = ["tests"]
"""
        )

        return project_dir

    @pytest.fixture
    def project_id(self, db, project_root):
        """Create test project."""
        return db.create_project(
            name="Quality Tracker Test Project",
            description="Test project for quality tracking",
            workspace_path=str(project_root),
        )

    @pytest.fixture
    def task(self, db, project_id):
        """Create test task."""
        cursor = db.conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (project_id, task_number, title, description, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                project_id,
                "1.1.1",
                "Test quality tracking",
                "Integration test for quality tracking",
                "in_progress",
            ),
        )
        db.conn.commit()
        task_id = cursor.lastrowid

        return Task(
            id=task_id,
            project_id=project_id,
            task_number="1.1.1",
            title="Test quality tracking",
            description="Integration test for quality tracking",
            status=TaskStatus.IN_PROGRESS,
        )

    @pytest.fixture
    def agent(self, db):
        """Create worker agent."""
        return WorkerAgent(
            agent_id="test-agent-001",
            agent_type="backend",
            provider="anthropic",
            maturity=AgentMaturity.D2,
            db=db,
        )


class TestQualityMetricsRecording(TestQualityTrackerIntegration):
    """Test 1: Quality metrics recorded after task completion."""

    @pytest.mark.asyncio
    async def test_metrics_recorded_after_quality_gates_pass(
        self, agent, task, project_root
    ):
        """Test that quality metrics are recorded when quality gates pass."""
        # Setup: Create mock quality result
        from codeframe.core.models import QualityGateResult

        mock_result = QualityGateResult(
            task_id=task.id,
            status="passed",
            failures=[],
            execution_time_seconds=1.5,
        )

        # Mock the quality gates run_all_gates method
        with patch.object(
            agent, "_ensure_quality_tracker"
        ) as mock_tracker_init, patch(
            "codeframe.lib.quality_gates.QualityGates.run_all_gates",
            new_callable=AsyncMock,
        ) as mock_gates:
            mock_gates.return_value = mock_result

            # Create a mock tracker
            mock_tracker = Mock(spec=QualityTracker)
            mock_tracker.check_degradation.return_value = {"has_degradation": False}
            mock_tracker_init.return_value = mock_tracker

            # Execute complete_task
            result = await agent.complete_task(task, project_root)

            # Verify metrics were recorded
            assert result["success"] is True
            assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_response_count_incremented_on_execute_task(self, agent, task):
        """Test that response count is incremented when execute_task completes."""
        initial_count = agent.response_count

        # Mock the LLM call to avoid actual API calls
        with patch.object(
            agent, "_call_llm_with_retry", new_callable=AsyncMock
        ) as mock_llm:
            mock_response = Mock()
            mock_response.content = [Mock(text="Task completed successfully")]
            mock_response.usage = Mock(input_tokens=100, output_tokens=200)
            mock_llm.return_value = mock_response

            # Execute task with mocked API key
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
                result = await agent.execute_task(task)

            # Verify response count incremented
            assert agent.response_count == initial_count + 1
            assert result["status"] == "completed"


class TestQualityDegradationDetection(TestQualityTrackerIntegration):
    """Test 2: Degradation detected and blocker created."""

    @pytest.mark.asyncio
    async def test_blocker_created_on_degradation(self, agent, task, project_root):
        """Test that a blocker is created when quality degradation is detected."""
        from codeframe.core.models import QualityGateResult

        mock_result = QualityGateResult(
            task_id=task.id,
            status="passed",  # Gates pass but degradation detected
            failures=[],
            execution_time_seconds=1.5,
        )

        degradation_result = {
            "has_degradation": True,
            "coverage_drop": 15.0,
            "pass_rate_drop": 5.0,
            "issues": [
                "Coverage: 70.0% (peak: 85.0%, drop: 15.0%)",
            ],
            "recommendation": "Consider context reset - quality has degraded significantly",
        }

        with patch(
            "codeframe.lib.quality_gates.QualityGates.run_all_gates",
            new_callable=AsyncMock,
        ) as mock_gates, patch.object(
            agent, "_ensure_quality_tracker"
        ) as mock_tracker_init:
            mock_gates.return_value = mock_result

            # Create mock tracker that returns degradation
            mock_tracker = Mock(spec=QualityTracker)
            mock_tracker.check_degradation.return_value = degradation_result
            mock_tracker_init.return_value = mock_tracker

            # Execute complete_task
            result = await agent.complete_task(task, project_root)

            # Verify blocker was created
            assert result["success"] is False
            assert result["status"] == "blocked"
            assert "degradation" in result
            assert result["degradation"]["has_degradation"] is True
            assert "blocker_id" in result


class TestContextResetRecommendation(TestQualityTrackerIntegration):
    """Test 3: Context reset recommended when quality degrades."""

    @pytest.mark.asyncio
    async def test_context_reset_recommended_high_response_count(self, agent, task):
        """Test that context reset is recommended when response count is high."""
        # Set high response count
        agent.response_count = 25
        agent.current_task = task

        with patch.object(agent, "_ensure_quality_tracker") as mock_init:
            # Return None to test fallback behavior
            mock_init.return_value = None

            result = await agent.should_recommend_context_reset(max_responses=20)

            assert result["should_reset"] is True
            assert len(result["reasons"]) > 0
            assert "Response count" in result["reasons"][0]

    @pytest.mark.asyncio
    async def test_context_reset_recommended_quality_degradation(
        self, agent, task, project_root
    ):
        """Test that context reset is recommended when quality degrades."""
        agent.response_count = 10
        agent.current_task = task

        with patch.object(agent, "_ensure_quality_tracker") as mock_init:
            mock_tracker = Mock(spec=QualityTracker)
            mock_tracker.should_reset_context.return_value = {
                "should_reset": True,
                "reasons": ["Quality degradation detected"],
                "recommendation": "Context reset recommended",
            }
            mock_init.return_value = mock_tracker

            result = await agent.should_recommend_context_reset()

            assert result["should_reset"] is True
            assert "Quality degradation" in result["reasons"][0]

    @pytest.mark.asyncio
    async def test_no_reset_recommended_healthy_context(self, agent, task):
        """Test that context reset is not recommended when quality is healthy."""
        agent.response_count = 5
        agent.current_task = task

        with patch.object(agent, "_ensure_quality_tracker") as mock_init:
            mock_tracker = Mock(spec=QualityTracker)
            mock_tracker.should_reset_context.return_value = {
                "should_reset": False,
                "reasons": [],
                "recommendation": "Context can continue",
            }
            mock_init.return_value = mock_tracker

            result = await agent.should_recommend_context_reset()

            assert result["should_reset"] is False
            assert len(result["reasons"]) == 0


class TestCheckpointQualityMetrics(TestQualityTrackerIntegration):
    """Test 4: Checkpoint includes quality metrics."""

    def test_checkpoint_metadata_includes_quality_stats(self, db, project_id, project_root):
        """Test that checkpoint metadata includes quality stats."""
        # Create quality history
        tracker = QualityTracker(project_path=str(project_root))
        tracker.record(
            QualityMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                response_count=5,
                test_pass_rate=95.0,
                coverage_percentage=87.5,
                total_tests=100,
                passed_tests=95,
                failed_tests=5,
                language="python",
                framework="pytest",
            )
        )

        # Create checkpoint with mocked git operations
        manager = CheckpointManager(
            db=db, project_root=project_root, project_id=project_id
        )

        # Mock git commit creation to avoid signing issues in test environment
        with patch.object(
            manager, "_create_git_commit", return_value="abc1234567890abcdef1234567890abcdef12"
        ):
            checkpoint = manager.create_checkpoint(
                name="Test checkpoint", description="Testing quality metrics"
            )

        # Verify quality stats in metadata
        assert checkpoint.metadata.quality_stats is not None
        assert checkpoint.metadata.quality_stats.get("current") is not None
        assert checkpoint.metadata.quality_stats.get("peak") is not None
        assert checkpoint.metadata.quality_trend is not None


class TestQualityTrackerEnsure(TestQualityTrackerIntegration):
    """Test _ensure_quality_tracker helper method."""

    def test_ensure_quality_tracker_returns_none_without_db(self):
        """Test that _ensure_quality_tracker returns None without database."""
        agent = WorkerAgent(
            agent_id="test-agent",
            agent_type="backend",
            provider="anthropic",
            db=None,  # No database
        )

        result = agent._ensure_quality_tracker()
        assert result is None

    def test_ensure_quality_tracker_returns_none_without_task(self, db):
        """Test that _ensure_quality_tracker returns None without current task."""
        agent = WorkerAgent(
            agent_id="test-agent",
            agent_type="backend",
            provider="anthropic",
            db=db,
        )
        # No current_task set

        result = agent._ensure_quality_tracker()
        assert result is None

    def test_ensure_quality_tracker_initializes_successfully(
        self, agent, task, project_root
    ):
        """Test that _ensure_quality_tracker initializes tracker with valid context."""
        agent.current_task = task

        tracker = agent._ensure_quality_tracker()

        assert tracker is not None
        assert isinstance(tracker, QualityTracker)

    def test_ensure_quality_tracker_caches_instance(self, agent, task, project_root):
        """Test that _ensure_quality_tracker returns cached instance."""
        agent.current_task = task

        tracker1 = agent._ensure_quality_tracker()
        tracker2 = agent._ensure_quality_tracker()

        assert tracker1 is tracker2  # Same instance


class TestQualityTrackerWithRealTracker(TestQualityTrackerIntegration):
    """Tests using real QualityTracker (not mocked)."""

    def test_quality_history_file_created(self, project_root):
        """Test that quality history file is created when recording metrics."""
        tracker = QualityTracker(project_path=str(project_root))

        # Record metrics
        tracker.record(
            QualityMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                response_count=1,
                test_pass_rate=100.0,
                coverage_percentage=90.0,
                total_tests=10,
                passed_tests=10,
                failed_tests=0,
                language="python",
                framework="pytest",
            )
        )

        # Verify file exists
        history_file = project_root / ".codeframe" / "quality_history.json"
        assert history_file.exists()

        # Verify content
        history = tracker.load_history()
        assert len(history) == 1
        assert history[0]["test_pass_rate"] == 100.0

    def test_degradation_detected_after_quality_drop(self, project_root):
        """Test that degradation is detected when quality drops significantly."""
        tracker = QualityTracker(project_path=str(project_root))

        # Record good metrics (peak)
        tracker.record(
            QualityMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                response_count=1,
                test_pass_rate=100.0,
                coverage_percentage=90.0,
                total_tests=10,
                passed_tests=10,
                failed_tests=0,
            )
        )

        # Record degraded metrics
        tracker.record(
            QualityMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                response_count=5,
                test_pass_rate=80.0,  # 20% drop
                coverage_percentage=75.0,  # 15% drop
                total_tests=10,
                passed_tests=8,
                failed_tests=2,
            )
        )

        # Check degradation
        result = tracker.check_degradation(threshold_percent=10.0)

        assert result["has_degradation"] is True
        assert "issues" in result
        assert len(result["issues"]) > 0

    def test_no_degradation_when_quality_stable(self, project_root):
        """Test that no degradation is detected when quality is stable."""
        tracker = QualityTracker(project_path=str(project_root))

        # Record consistent metrics
        for i in range(3):
            tracker.record(
                QualityMetrics(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    response_count=i + 1,
                    test_pass_rate=95.0,
                    coverage_percentage=88.0,
                    total_tests=100,
                    passed_tests=95,
                    failed_tests=5,
                )
            )

        # Check degradation
        result = tracker.check_degradation(threshold_percent=10.0)

        assert result["has_degradation"] is False
