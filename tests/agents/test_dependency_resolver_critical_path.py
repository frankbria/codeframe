"""Tests for Critical Path Analysis in DependencyResolver.

TDD tests for enhanced dependency analysis features:
- Critical path calculation (longest path through DAG)
- Task slack/float time calculation
- Parallel execution opportunity identification
- Dependency conflict detection and resolution
"""

import pytest
from codeframe.agents.dependency_resolver import DependencyResolver
from codeframe.core.models import Task, TaskStatus

pytestmark = pytest.mark.v2


@pytest.fixture
def resolver():
    """Fresh DependencyResolver instance."""
    return DependencyResolver()


@pytest.fixture
def linear_tasks():
    """Create a simple linear task chain: A -> B -> C -> D."""
    return [
        Task(id=1, task_number="1.1", title="Task A", status=TaskStatus.PENDING, depends_on=""),
        Task(id=2, task_number="1.2", title="Task B", status=TaskStatus.PENDING, depends_on="1"),
        Task(id=3, task_number="1.3", title="Task C", status=TaskStatus.PENDING, depends_on="2"),
        Task(id=4, task_number="1.4", title="Task D", status=TaskStatus.PENDING, depends_on="3"),
    ]


@pytest.fixture
def parallel_tasks():
    """Create tasks with parallel opportunities: A -> (B, C) -> D."""
    return [
        Task(id=1, task_number="1.1", title="Task A", status=TaskStatus.PENDING, depends_on=""),
        Task(id=2, task_number="1.2", title="Task B", status=TaskStatus.PENDING, depends_on="1"),
        Task(id=3, task_number="1.3", title="Task C", status=TaskStatus.PENDING, depends_on="1"),
        Task(id=4, task_number="1.4", title="Task D", status=TaskStatus.PENDING, depends_on="2,3"),
    ]


@pytest.fixture
def complex_tasks():
    """Create a more complex DAG with multiple paths.

    Structure:
       A (2h)
      / \\
    B(3h) C(1h)
      \\   /
       D(2h)
         |
       E(1h)

    Critical path: A -> B -> D -> E = 2 + 3 + 2 + 1 = 8 hours
    """
    return [
        Task(id=1, task_number="1.1", title="Task A", status=TaskStatus.PENDING, depends_on=""),
        Task(id=2, task_number="1.2", title="Task B", status=TaskStatus.PENDING, depends_on="1"),
        Task(id=3, task_number="1.3", title="Task C", status=TaskStatus.PENDING, depends_on="1"),
        Task(id=4, task_number="1.4", title="Task D", status=TaskStatus.PENDING, depends_on="2,3"),
        Task(id=5, task_number="1.5", title="Task E", status=TaskStatus.PENDING, depends_on="4"),
    ]


@pytest.mark.unit
class TestCriticalPathCalculation:
    """Test critical path algorithm implementation."""

    def test_calculate_critical_path_returns_result_object(self, resolver, linear_tasks):
        """Test that calculate_critical_path returns a CriticalPathResult."""
        resolver.build_dependency_graph(linear_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0}

        result = resolver.calculate_critical_path(durations)

        assert hasattr(result, "critical_task_ids")
        assert hasattr(result, "total_duration")
        assert hasattr(result, "task_timings")

    def test_critical_path_linear_chain(self, resolver, linear_tasks):
        """Test critical path for linear chain (all tasks on critical path)."""
        resolver.build_dependency_graph(linear_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0}

        result = resolver.calculate_critical_path(durations)

        # All tasks should be on critical path in linear chain
        assert set(result.critical_task_ids) == {1, 2, 3, 4}
        # Total duration = 2 + 3 + 1 + 2 = 8 hours
        assert result.total_duration == 8.0

    def test_critical_path_with_parallel_branches(self, resolver, complex_tasks):
        """Test critical path identifies longest path through DAG."""
        resolver.build_dependency_graph(complex_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0, 5: 1.0}

        result = resolver.calculate_critical_path(durations)

        # Critical path: A -> B -> D -> E (not C, as it's shorter)
        assert 1 in result.critical_task_ids  # A
        assert 2 in result.critical_task_ids  # B (longer than C)
        assert 4 in result.critical_task_ids  # D
        assert 5 in result.critical_task_ids  # E
        assert 3 not in result.critical_task_ids  # C is not on critical path

        # Total: 2 + 3 + 2 + 1 = 8 hours
        assert result.total_duration == 8.0

    def test_critical_path_task_timings_include_start_finish(self, resolver, linear_tasks):
        """Test that task_timings includes early/late start and finish times."""
        resolver.build_dependency_graph(linear_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0}

        result = resolver.calculate_critical_path(durations)

        # Task 1: starts at 0, finishes at 2
        assert result.task_timings[1].earliest_start == 0
        assert result.task_timings[1].earliest_finish == 2.0

        # Task 2: starts at 2, finishes at 5
        assert result.task_timings[2].earliest_start == 2.0
        assert result.task_timings[2].earliest_finish == 5.0

    def test_critical_path_handles_missing_duration(self, resolver, linear_tasks):
        """Test that missing durations default to 0."""
        resolver.build_dependency_graph(linear_tasks)
        durations = {1: 2.0, 2: 3.0}  # Missing tasks 3 and 4

        result = resolver.calculate_critical_path(durations)

        # Should handle gracefully with default durations
        assert result is not None
        assert result.total_duration >= 5.0  # At least A + B


@pytest.mark.unit
class TestSlackCalculation:
    """Test task slack/float time calculation."""

    def test_calculate_task_slack_linear_chain(self, resolver, linear_tasks):
        """Test that linear chain has zero slack for all tasks."""
        resolver.build_dependency_graph(linear_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0}

        slack = resolver.calculate_task_slack(durations)

        # All tasks in linear chain should have zero slack
        for task_id in [1, 2, 3, 4]:
            assert slack[task_id] == 0.0

    def test_calculate_task_slack_with_parallel_paths(self, resolver, complex_tasks):
        """Test that non-critical path has positive slack."""
        resolver.build_dependency_graph(complex_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0, 5: 1.0}

        slack = resolver.calculate_task_slack(durations)

        # Tasks on critical path should have zero slack
        assert slack[1] == 0.0  # A
        assert slack[2] == 0.0  # B
        assert slack[4] == 0.0  # D
        assert slack[5] == 0.0  # E

        # Task C has slack (can be delayed without affecting project end)
        # C duration is 1, B duration is 3, so C has 2 hours of slack
        assert slack[3] == 2.0

    def test_slack_dict_keys_match_all_tasks(self, resolver, complex_tasks):
        """Test that slack dict contains all task IDs."""
        resolver.build_dependency_graph(complex_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0, 5: 1.0}

        slack = resolver.calculate_task_slack(durations)

        assert set(slack.keys()) == {1, 2, 3, 4, 5}


@pytest.mark.unit
class TestParallelOpportunities:
    """Test parallel execution opportunity identification."""

    def test_identify_parallel_opportunities_returns_waves(self, resolver, parallel_tasks):
        """Test that method returns dict of execution waves."""
        resolver.build_dependency_graph(parallel_tasks)

        waves = resolver.identify_parallel_opportunities()

        assert isinstance(waves, dict)
        # Wave 0: tasks with no dependencies
        assert 0 in waves
        assert 1 in waves[0]  # Task A

    def test_parallel_tasks_in_same_wave(self, resolver, parallel_tasks):
        """Test that parallel tasks are grouped in same wave."""
        resolver.build_dependency_graph(parallel_tasks)

        waves = resolver.identify_parallel_opportunities()

        # Wave 0: A (no deps)
        assert 1 in waves[0]

        # Wave 1: B and C (both depend only on A)
        wave_1_tasks = waves.get(1, [])
        assert 2 in wave_1_tasks
        assert 3 in wave_1_tasks

        # Wave 2: D (depends on B and C)
        wave_2_tasks = waves.get(2, [])
        assert 4 in wave_2_tasks

    def test_linear_chain_has_no_parallel(self, resolver, linear_tasks):
        """Test that linear chain has one task per wave."""
        resolver.build_dependency_graph(linear_tasks)

        waves = resolver.identify_parallel_opportunities()

        # Each wave should have exactly one task
        assert len(waves[0]) == 1
        assert len(waves[1]) == 1
        assert len(waves[2]) == 1
        assert len(waves[3]) == 1


@pytest.mark.unit
class TestDependencyConflictDetection:
    """Test dependency conflict and bottleneck detection."""

    def test_detect_dependency_conflicts_returns_list(self, resolver, complex_tasks):
        """Test that method returns list of conflicts."""
        resolver.build_dependency_graph(complex_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0, 5: 1.0}

        conflicts = resolver.detect_dependency_conflicts(durations)

        assert isinstance(conflicts, list)

    def test_detect_bottleneck_task(self, resolver):
        """Test detection of bottleneck task (many dependents)."""
        # Create a bottleneck: A has many dependents
        tasks = [
            Task(id=1, task_number="1.1", title="Bottleneck", status=TaskStatus.PENDING, depends_on=""),
            Task(id=2, task_number="1.2", title="B", status=TaskStatus.PENDING, depends_on="1"),
            Task(id=3, task_number="1.3", title="C", status=TaskStatus.PENDING, depends_on="1"),
            Task(id=4, task_number="1.4", title="D", status=TaskStatus.PENDING, depends_on="1"),
            Task(id=5, task_number="1.5", title="E", status=TaskStatus.PENDING, depends_on="1"),
        ]
        resolver.build_dependency_graph(tasks)
        durations = {1: 5.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0}

        conflicts = resolver.detect_dependency_conflicts(durations)

        # Should detect task 1 as a bottleneck
        bottleneck_ids = [c.task_id for c in conflicts if c.conflict_type == "bottleneck"]
        assert 1 in bottleneck_ids

    def test_detect_long_dependency_chain(self, resolver):
        """Test detection of long dependency chains (> 5 tasks)."""
        # Create a long chain: A -> B -> C -> D -> E -> F -> G
        tasks = [
            Task(id=i, task_number=f"1.{i}", title=f"Task {i}", status=TaskStatus.PENDING,
                 depends_on="" if i == 1 else str(i-1))
            for i in range(1, 8)
        ]
        resolver.build_dependency_graph(tasks)
        durations = {i: 1.0 for i in range(1, 8)}

        conflicts = resolver.detect_dependency_conflicts(durations)

        # Should detect long chain
        chain_conflicts = [c for c in conflicts if c.conflict_type == "long_chain"]
        assert len(chain_conflicts) > 0

    def test_conflict_includes_severity_and_recommendations(self, resolver, complex_tasks):
        """Test that conflicts include severity and recommendations."""
        resolver.build_dependency_graph(complex_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0, 5: 1.0}

        conflicts = resolver.detect_dependency_conflicts(durations)

        for conflict in conflicts:
            assert hasattr(conflict, "severity")
            assert conflict.severity in ["critical", "high", "medium"]
            assert hasattr(conflict, "recommendation")


@pytest.mark.unit
class TestResolutionSuggestions:
    """Test dependency resolution suggestion generation."""

    def test_suggest_dependency_resolution_for_bottleneck(self, resolver):
        """Test resolution suggestions for bottleneck."""
        # Create bottleneck scenario
        tasks = [
            Task(id=1, task_number="1.1", title="Bottleneck", status=TaskStatus.PENDING, depends_on=""),
            Task(id=2, task_number="1.2", title="B", status=TaskStatus.PENDING, depends_on="1"),
            Task(id=3, task_number="1.3", title="C", status=TaskStatus.PENDING, depends_on="1"),
            Task(id=4, task_number="1.4", title="D", status=TaskStatus.PENDING, depends_on="1"),
        ]
        resolver.build_dependency_graph(tasks)
        durations = {1: 8.0, 2: 1.0, 3: 1.0, 4: 1.0}

        conflicts = resolver.detect_dependency_conflicts(durations)
        suggestions = resolver.suggest_dependency_resolution(conflicts)

        assert isinstance(suggestions, list)
        # Should suggest task splitting or prioritization
        if suggestions:
            assert hasattr(suggestions[0], "suggestion_type")
            assert hasattr(suggestions[0], "description")


@pytest.mark.unit
class TestCriticalPathResultDataclass:
    """Test CriticalPathResult dataclass structure."""

    def test_critical_path_result_has_required_fields(self, resolver, linear_tasks):
        """Test CriticalPathResult dataclass has all required fields."""
        resolver.build_dependency_graph(linear_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0}

        result = resolver.calculate_critical_path(durations)

        # Required fields
        assert isinstance(result.critical_task_ids, list)
        assert isinstance(result.total_duration, (int, float))
        assert isinstance(result.task_timings, dict)

    def test_task_timing_has_required_fields(self, resolver, linear_tasks):
        """Test TaskTiming dataclass has timing fields."""
        resolver.build_dependency_graph(linear_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0}

        result = resolver.calculate_critical_path(durations)
        timing = result.task_timings[1]

        assert hasattr(timing, "earliest_start")
        assert hasattr(timing, "earliest_finish")
        assert hasattr(timing, "latest_start")
        assert hasattr(timing, "latest_finish")


@pytest.mark.unit
class TestDependencyConflictDataclass:
    """Test DependencyConflict dataclass structure."""

    def test_dependency_conflict_has_required_fields(self, resolver):
        """Test DependencyConflict dataclass has required fields."""
        tasks = [
            Task(id=1, task_number="1.1", title="A", status=TaskStatus.PENDING, depends_on=""),
            Task(id=2, task_number="1.2", title="B", status=TaskStatus.PENDING, depends_on="1"),
            Task(id=3, task_number="1.3", title="C", status=TaskStatus.PENDING, depends_on="1"),
            Task(id=4, task_number="1.4", title="D", status=TaskStatus.PENDING, depends_on="1"),
        ]
        resolver.build_dependency_graph(tasks)
        durations = {1: 5.0, 2: 1.0, 3: 1.0, 4: 1.0}

        conflicts = resolver.detect_dependency_conflicts(durations)

        if conflicts:
            conflict = conflicts[0]
            assert hasattr(conflict, "task_id")
            assert hasattr(conflict, "conflict_type")
            assert hasattr(conflict, "severity")
            assert hasattr(conflict, "recommendation")
            assert hasattr(conflict, "impact_analysis")
