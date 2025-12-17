"""Tests for LeadAgent bottleneck detection functionality."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from codeframe.agents.lead_agent import LeadAgent
from codeframe.persistence.database import Database


@pytest.fixture
def db():
    """Create mock database."""
    return Mock(spec=Database)


@pytest.fixture
def lead_agent(db):
    """Create LeadAgent with mocked dependencies."""
    with patch("codeframe.agents.lead_agent.AnthropicProvider"):
        with patch("codeframe.agents.lead_agent.DiscoveryQuestionFramework"):
            with patch("codeframe.agents.lead_agent.AnswerCapture"):
                with patch("codeframe.agents.lead_agent.AgentPoolManager"):
                    with patch("codeframe.agents.lead_agent.DependencyResolver"):
                        with patch("codeframe.agents.lead_agent.SimpleAgentAssigner"):
                            agent = LeadAgent(
                                project_id=1,
                                db=db,
                                api_key="test-key",
                                max_agents=5,
                            )
                            return agent


class TestCalculateWaitTime:
    """Tests for _calculate_wait_time helper method."""

    def test_calculate_wait_time_valid(self, lead_agent):
        """Test wait time calculation with valid timestamp."""
        now = datetime.now()
        past = now - timedelta(minutes=45)

        task = {"id": 1, "created_at": past.isoformat()}
        wait_time = lead_agent._calculate_wait_time(task)

        # Should be approximately 45 minutes
        assert 40 <= wait_time <= 50

    def test_calculate_wait_time_zero_minutes(self, lead_agent):
        """Test wait time calculation with recent task."""
        now = datetime.now()
        task = {"id": 1, "created_at": now.isoformat()}
        wait_time = lead_agent._calculate_wait_time(task)

        assert wait_time == 0

    def test_calculate_wait_time_missing_timestamp(self, lead_agent):
        """Test wait time calculation with missing created_at."""
        task = {"id": 1}
        wait_time = lead_agent._calculate_wait_time(task)

        assert wait_time == 0

    def test_calculate_wait_time_invalid_timestamp(self, lead_agent):
        """Test wait time calculation with invalid timestamp format."""
        task = {"id": 1, "created_at": "invalid-date"}
        wait_time = lead_agent._calculate_wait_time(task)

        assert wait_time == 0

    def test_calculate_wait_time_future_timestamp(self, lead_agent):
        """Test wait time calculation with future timestamp."""
        future = datetime.now() + timedelta(minutes=10)
        task = {"id": 1, "created_at": future.isoformat()}
        wait_time = lead_agent._calculate_wait_time(task)

        # Should return 0 or negative (clamped to 0)
        assert wait_time == 0


class TestGetAgentWorkload:
    """Tests for _get_agent_workload helper method."""

    def test_get_agent_workload_busy_agents(self, lead_agent):
        """Test workload calculation with busy agents."""
        lead_agent.agent_pool_manager.get_agent_status.return_value = {
            "agent-1": {"status": "busy", "tasks_completed": 2},
            "agent-2": {"status": "idle", "tasks_completed": 5},
            "agent-3": {"status": "busy", "tasks_completed": 1},
        }

        workload = lead_agent._get_agent_workload()

        assert workload["agent-1"] == 1  # Busy = 1 task (current)
        assert workload["agent-2"] == 0  # idle
        assert workload["agent-3"] == 1  # Busy = 1 task (current)

    def test_get_agent_workload_no_agents(self, lead_agent):
        """Test workload calculation with no agents."""
        lead_agent.agent_pool_manager.get_agent_status.return_value = {}

        workload = lead_agent._get_agent_workload()

        assert workload == {}

    def test_get_agent_workload_exception_handling(self, lead_agent):
        """Test workload calculation handles exceptions gracefully."""
        lead_agent.agent_pool_manager.get_agent_status.side_effect = Exception("Pool error")

        workload = lead_agent._get_agent_workload()

        assert workload == {}


class TestGetBlockingRelationships:
    """Tests for _get_blocking_relationships helper method."""

    def test_get_blocking_relationships_success(self, lead_agent):
        """Test getting blocking relationships successfully."""
        expected_blocked = {1: [2, 3], 4: [5]}
        lead_agent.dependency_resolver.get_blocked_tasks.return_value = expected_blocked

        blocked = lead_agent._get_blocking_relationships()

        assert blocked == expected_blocked

    def test_get_blocking_relationships_no_blockers(self, lead_agent):
        """Test getting blocking relationships with no blockers."""
        lead_agent.dependency_resolver.get_blocked_tasks.return_value = {}

        blocked = lead_agent._get_blocking_relationships()

        assert blocked == {}

    def test_get_blocking_relationships_exception_handling(self, lead_agent):
        """Test blocking relationships handles exceptions gracefully."""
        lead_agent.dependency_resolver.get_blocked_tasks.side_effect = Exception("Graph error")

        blocked = lead_agent._get_blocking_relationships()

        assert blocked == {}


class TestDetermineSeverity:
    """Tests for _determine_severity helper method."""

    def test_dependency_wait_critical(self, lead_agent):
        """Test severity determination for critical wait time."""
        severity = lead_agent._determine_severity(
            "dependency_wait", {"wait_time_minutes": 125}
        )
        assert severity == "critical"

    def test_dependency_wait_high(self, lead_agent):
        """Test severity determination for high wait time."""
        severity = lead_agent._determine_severity(
            "dependency_wait", {"wait_time_minutes": 90}
        )
        assert severity == "high"

    def test_dependency_wait_medium(self, lead_agent):
        """Test severity determination for medium wait time."""
        severity = lead_agent._determine_severity(
            "dependency_wait", {"wait_time_minutes": 45}
        )
        assert severity == "medium"

    def test_agent_overload_high(self, lead_agent):
        """Test severity determination for high agent overload."""
        severity = lead_agent._determine_severity(
            "agent_overload", {"assigned_tasks": 10}
        )
        assert severity == "high"

    def test_agent_overload_medium(self, lead_agent):
        """Test severity determination for medium agent overload."""
        severity = lead_agent._determine_severity(
            "agent_overload", {"assigned_tasks": 7}
        )
        assert severity == "medium"

    def test_agent_overload_low(self, lead_agent):
        """Test severity determination for low agent overload."""
        severity = lead_agent._determine_severity(
            "agent_overload", {"assigned_tasks": 3}
        )
        assert severity == "low"

    def test_agent_idle(self, lead_agent):
        """Test severity determination for idle agents."""
        severity = lead_agent._determine_severity("agent_idle", {})
        assert severity == "medium"

    def test_critical_path_critical(self, lead_agent):
        """Test severity determination for critical path (5+ dependents)."""
        severity = lead_agent._determine_severity(
            "critical_path", {"blocked_dependents": 6}
        )
        assert severity == "critical"

    def test_critical_path_high(self, lead_agent):
        """Test severity determination for high critical path."""
        severity = lead_agent._determine_severity(
            "critical_path", {"blocked_dependents": 4}
        )
        assert severity == "high"

    def test_critical_path_medium(self, lead_agent):
        """Test severity determination for medium critical path."""
        severity = lead_agent._determine_severity(
            "critical_path", {"blocked_dependents": 2}
        )
        assert severity == "medium"

    def test_unknown_type(self, lead_agent):
        """Test severity determination for unknown type."""
        severity = lead_agent._determine_severity("unknown", {})
        assert severity == "low"


class TestGenerateRecommendation:
    """Tests for _generate_recommendation helper method."""

    def test_recommendation_dependency_wait(self, lead_agent):
        """Test recommendation for dependency wait bottleneck."""
        bottleneck = {
            "type": "dependency_wait",
            "task_id": 5,
            "blocking_task_id": 3,
            "wait_time_minutes": 90,
        }
        rec = lead_agent._generate_recommendation(bottleneck)

        assert "Task 5" in rec
        assert "90" in rec
        assert "task 3" in rec
        assert "Investigate" in rec

    def test_recommendation_agent_overload(self, lead_agent):
        """Test recommendation for agent overload bottleneck."""
        bottleneck = {
            "type": "agent_overload",
            "agent_id": "worker-1",
            "assigned_tasks": 8,
        }
        rec = lead_agent._generate_recommendation(bottleneck)

        assert "worker-1" in rec
        assert "8" in rec
        assert "overloaded" in rec

    def test_recommendation_agent_idle(self, lead_agent):
        """Test recommendation for agent idle bottleneck."""
        bottleneck = {
            "type": "agent_idle",
            "idle_agents": ["agent-1", "agent-2"],
        }
        rec = lead_agent._generate_recommendation(bottleneck)

        assert "agent-1" in rec
        assert "agent-2" in rec
        assert "idle" in rec

    def test_recommendation_critical_path(self, lead_agent):
        """Test recommendation for critical path bottleneck."""
        bottleneck = {
            "type": "critical_path",
            "task_id": 10,
            "blocked_dependents": 5,
        }
        rec = lead_agent._generate_recommendation(bottleneck)

        assert "Task 10" in rec
        assert "5" in rec
        assert "block" in rec.lower()

    def test_recommendation_unknown_type(self, lead_agent):
        """Test recommendation for unknown bottleneck type."""
        bottleneck = {"type": "unknown"}
        rec = lead_agent._generate_recommendation(bottleneck)

        assert "Unknown" in rec


class TestDetectBottlenecks:
    """Tests for detect_bottlenecks main method."""

    def test_detect_no_tasks(self, lead_agent):
        """Test bottleneck detection with no tasks."""
        lead_agent.db.get_project_tasks.return_value = []

        bottlenecks = lead_agent.detect_bottlenecks()

        assert bottlenecks == []

    def test_detect_dependency_wait_bottleneck(self, lead_agent):
        """Test detection of dependency wait bottleneck."""
        past = datetime.now() - timedelta(minutes=90)
        tasks = [
            {
                "id": 1,
                "status": "blocked",
                "created_at": past.isoformat(),
                "title": "Task 1",
            }
        ]

        lead_agent.db.get_project_tasks.return_value = tasks
        lead_agent.agent_pool_manager.get_agent_status.return_value = {}
        lead_agent.dependency_resolver.get_blocked_tasks.return_value = {1: [2]}
        lead_agent.dependency_resolver.dependents = {}

        bottlenecks = lead_agent.detect_bottlenecks()

        assert len(bottlenecks) == 1
        assert bottlenecks[0]["type"] == "dependency_wait"
        assert bottlenecks[0]["task_id"] == 1
        assert bottlenecks[0]["severity"] == "high"

    def test_detect_agent_overload_bottleneck(self, lead_agent):
        """Test detection of agent overload bottleneck.

        Note: Current architecture supports 1 task per agent at a time.
        Agent overload detection is reserved for future when agents support task queues.
        This test verifies the detection logic works if workload > threshold.
        """
        tasks = [
            {"id": 1, "status": "pending", "created_at": datetime.now().isoformat()},
            {"id": 2, "status": "pending", "created_at": datetime.now().isoformat()},
        ]

        lead_agent.db.get_project_tasks.return_value = tasks
        # Mock an agent with artificially high workload (simulating future queue-based architecture)
        # In real usage, workload is always 0 or 1, so this bottleneck won't trigger
        lead_agent._get_agent_workload = lambda: {"agent-1": 6}  # Override for test
        lead_agent.dependency_resolver.get_blocked_tasks.return_value = {}
        lead_agent.dependency_resolver.dependents = {}

        bottlenecks = lead_agent.detect_bottlenecks()

        assert any(bn["type"] == "agent_overload" for bn in bottlenecks)
        overload_bn = next(bn for bn in bottlenecks if bn["type"] == "agent_overload")
        assert overload_bn["assigned_tasks"] == 6
        assert overload_bn["severity"] in ["medium", "high"]

    def test_detect_agent_idle_bottleneck(self, lead_agent):
        """Test detection of agent idle bottleneck."""
        tasks = [
            {"id": 1, "status": "pending", "created_at": datetime.now().isoformat()},
        ]

        lead_agent.db.get_project_tasks.return_value = tasks
        lead_agent.agent_pool_manager.get_agent_status.return_value = {
            "agent-1": {"status": "idle"}
        }
        lead_agent.dependency_resolver.get_blocked_tasks.return_value = {}
        lead_agent.dependency_resolver.dependents = {}

        bottlenecks = lead_agent.detect_bottlenecks()

        assert any(bn["type"] == "agent_idle" for bn in bottlenecks)

    def test_detect_critical_path_bottleneck(self, lead_agent):
        """Test detection of critical path bottleneck."""
        tasks = [
            {"id": 1, "status": "in_progress", "created_at": datetime.now().isoformat()},
            {"id": 2, "status": "pending", "created_at": datetime.now().isoformat()},
            {"id": 3, "status": "pending", "created_at": datetime.now().isoformat()},
            {"id": 4, "status": "pending", "created_at": datetime.now().isoformat()},
            {"id": 5, "status": "pending", "created_at": datetime.now().isoformat()},
        ]

        lead_agent.db.get_project_tasks.return_value = tasks
        lead_agent.agent_pool_manager.get_agent_status.return_value = {}
        lead_agent.dependency_resolver.get_blocked_tasks.return_value = {}
        # Task 1 blocks tasks 2, 3, 4, 5 (4 dependents)
        lead_agent.dependency_resolver.dependents = {1: {2, 3, 4, 5}}

        bottlenecks = lead_agent.detect_bottlenecks()

        assert any(bn["type"] == "critical_path" for bn in bottlenecks)

    def test_detect_multiple_bottlenecks(self, lead_agent):
        """Test detection of multiple bottlenecks simultaneously."""
        past = datetime.now() - timedelta(minutes=90)
        tasks = [
            {
                "id": 1,
                "status": "blocked",
                "created_at": past.isoformat(),
                "title": "Blocked task",
            },
            {"id": 2, "status": "pending", "created_at": datetime.now().isoformat()},
            {"id": 3, "status": "pending", "created_at": datetime.now().isoformat()},
            {"id": 4, "status": "pending", "created_at": datetime.now().isoformat()},
            {"id": 5, "status": "pending", "created_at": datetime.now().isoformat()},
        ]

        lead_agent.db.get_project_tasks.return_value = tasks
        lead_agent.agent_pool_manager.get_agent_status.return_value = {
            "agent-1": {"status": "idle"}
        }
        lead_agent.dependency_resolver.get_blocked_tasks.return_value = {1: [6]}
        lead_agent.dependency_resolver.dependents = {1: {2, 3, 4, 5}}

        bottlenecks = lead_agent.detect_bottlenecks()

        # Should detect: dependency_wait (1), critical_path (1), agent_idle (1)
        types = [bn["type"] for bn in bottlenecks]
        assert "dependency_wait" in types
        assert "critical_path" in types
        assert "agent_idle" in types

    def test_detect_bottlenecks_exception_handling(self, lead_agent):
        """Test bottleneck detection handles exceptions gracefully."""
        lead_agent.db.get_project_tasks.side_effect = Exception("DB error")

        bottlenecks = lead_agent.detect_bottlenecks()

        assert bottlenecks == []

    def test_detect_bottlenecks_returns_recommendations(self, lead_agent):
        """Test that detected bottlenecks include recommendations."""
        past = datetime.now() - timedelta(minutes=90)
        tasks = [
            {
                "id": 1,
                "status": "blocked",
                "created_at": past.isoformat(),
            }
        ]

        lead_agent.db.get_project_tasks.return_value = tasks
        lead_agent.agent_pool_manager.get_agent_status.return_value = {}
        lead_agent.dependency_resolver.get_blocked_tasks.return_value = {1: [2]}
        lead_agent.dependency_resolver.dependents = {}

        bottlenecks = lead_agent.detect_bottlenecks()

        assert len(bottlenecks) > 0
        assert "recommendation" in bottlenecks[0]
        assert len(bottlenecks[0]["recommendation"]) > 0

    def test_bottleneck_has_severity(self, lead_agent):
        """Test that detected bottlenecks include severity level."""
        past = datetime.now() - timedelta(minutes=90)
        tasks = [
            {
                "id": 1,
                "status": "blocked",
                "created_at": past.isoformat(),
            }
        ]

        lead_agent.db.get_project_tasks.return_value = tasks
        lead_agent.agent_pool_manager.get_agent_status.return_value = {}
        lead_agent.dependency_resolver.get_blocked_tasks.return_value = {1: [2]}
        lead_agent.dependency_resolver.dependents = {}

        bottlenecks = lead_agent.detect_bottlenecks()

        assert len(bottlenecks) > 0
        assert bottlenecks[0]["severity"] in ["critical", "high", "medium", "low"]

    def test_skip_tasks_with_short_wait_time(self, lead_agent):
        """Test that tasks with short wait times are not flagged."""
        # Task created just now (< 60 min threshold)
        tasks = [
            {
                "id": 1,
                "status": "blocked",
                "created_at": datetime.now().isoformat(),
            }
        ]

        lead_agent.db.get_project_tasks.return_value = tasks
        lead_agent.agent_pool_manager.get_agent_status.return_value = {}
        lead_agent.dependency_resolver.get_blocked_tasks.return_value = {1: [2]}
        lead_agent.dependency_resolver.dependents = {}

        bottlenecks = lead_agent.detect_bottlenecks()

        # Should not have any dependency_wait bottlenecks
        assert not any(bn["type"] == "dependency_wait" for bn in bottlenecks)

    def test_skip_agents_below_threshold(self, lead_agent):
        """Test that agents below overload threshold are not flagged.

        Note: In current architecture, workload is 0 or 1, so overload won't trigger.
        This test verifies the detection logic works correctly for workload < threshold.
        """
        # Populate with realistic task dicts
        tasks = [
            {"id": 1, "status": "pending", "created_at": datetime.now().isoformat()},
            {"id": 2, "status": "assigned", "created_at": datetime.now().isoformat()},
            {"id": 3, "status": "in_progress", "created_at": datetime.now().isoformat()},
        ]

        lead_agent.db.get_project_tasks.return_value = tasks
        lead_agent.agent_pool_manager.get_agent_status.return_value = {
            "agent-1": {"status": "busy", "tasks_completed": 3, "current_task": 1}
        }
        # Mock workload below threshold (simulating future architecture with task queues)
        lead_agent._get_agent_workload = lambda: {"agent-1": 4}  # Below threshold of 5
        lead_agent.dependency_resolver.get_blocked_tasks.return_value = {}
        lead_agent.dependency_resolver.dependents = {}

        bottlenecks = lead_agent.detect_bottlenecks()

        # Should not have any agent_overload bottlenecks (workload 4 < threshold 5)
        assert not any(bn["type"] == "agent_overload" for bn in bottlenecks)
