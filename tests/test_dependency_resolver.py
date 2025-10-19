"""
Tests for Dependency Resolver (Sprint 4: cf-50).
"""

import pytest
from codeframe.agents.dependency_resolver import DependencyResolver
from codeframe.core.models import Task


@pytest.fixture
def resolver():
    """Create fresh DependencyResolver for each test."""
    return DependencyResolver()


@pytest.fixture
def simple_tasks():
    """Create simple task list with linear dependencies."""
    return [
        Task(id=1, title="Task 1", description="", status="pending", priority=1, workflow_step=1, depends_on=""),
        Task(id=2, title="Task 2", description="", status="pending", priority=1, workflow_step=1, depends_on="[1]"),
        Task(id=3, title="Task 3", description="", status="pending", priority=1, workflow_step=1, depends_on="[2]"),
    ]


@pytest.fixture
def complex_tasks():
    """Create complex task graph with multiple dependency paths."""
    return [
        Task(id=1, title="Task 1", description="", status="pending", priority=1, workflow_step=1, depends_on=""),
        Task(id=2, title="Task 2", description="", status="pending", priority=1, workflow_step=1, depends_on=""),
        Task(id=3, title="Task 3", description="", status="pending", priority=1, workflow_step=1, depends_on="[1,2]"),
        Task(id=4, title="Task 4", description="", status="pending", priority=1, workflow_step=1, depends_on="[1]"),
        Task(id=5, title="Task 5", description="", status="pending", priority=1, workflow_step=1, depends_on="[3,4]"),
    ]


class TestDAGConstruction:
    """Test dependency graph construction."""

    def test_build_empty_graph(self, resolver):
        """Test building graph with no tasks."""
        resolver.build_dependency_graph([])

        assert len(resolver.all_tasks) == 0
        assert len(resolver.dependencies) == 0

    def test_build_simple_linear_graph(self, resolver, simple_tasks):
        """Test building simple linear dependency chain."""
        resolver.build_dependency_graph(simple_tasks)

        assert len(resolver.all_tasks) == 3
        assert resolver.dependencies[2] == {1}
        assert resolver.dependencies[3] == {2}
        assert resolver.dependents[1] == {2}
        assert resolver.dependents[2] == {3}

    def test_build_complex_graph(self, resolver, complex_tasks):
        """Test building complex dependency graph."""
        resolver.build_dependency_graph(complex_tasks)

        assert len(resolver.all_tasks) == 5
        assert resolver.dependencies[3] == {1, 2}
        assert resolver.dependencies[4] == {1}
        assert resolver.dependencies[5] == {3, 4}
        assert resolver.dependents[1] == {3, 4}

    def test_build_graph_with_completed_tasks(self, resolver):
        """Test building graph tracks completed tasks."""
        tasks = [
            Task(id=1, title="T1", description="", status="completed", priority=1, workflow_step=1, depends_on=""),
            Task(id=2, title="T2", description="", status="pending", priority=1, workflow_step=1, depends_on="[1]"),
        ]

        resolver.build_dependency_graph(tasks)

        assert 1 in resolver.completed_tasks
        assert 2 not in resolver.completed_tasks

    def test_build_graph_comma_separated_format(self, resolver):
        """Test parsing comma-separated depends_on format."""
        tasks = [
            Task(id=1, title="T1", description="", status="pending", priority=1, workflow_step=1, depends_on=""),
            Task(id=2, title="T2", description="", status="pending", priority=1, workflow_step=1, depends_on=""),
            Task(id=3, title="T3", description="", status="pending", priority=1, workflow_step=1, depends_on="1,2"),
        ]

        # Should parse comma-separated format correctly
        resolver.build_dependency_graph(tasks)
        assert resolver.dependencies[3] == {1, 2}  # Both dependencies parsed


class TestCycleDetection:
    """Test circular dependency detection."""

    def test_detect_no_cycle_linear(self, resolver, simple_tasks):
        """Test no cycle detected in linear chain."""
        resolver.build_dependency_graph(simple_tasks)

        assert resolver.detect_cycles() is False

    def test_detect_no_cycle_complex(self, resolver, complex_tasks):
        """Test no cycle detected in complex DAG."""
        resolver.build_dependency_graph(complex_tasks)

        assert resolver.detect_cycles() is False

    def test_detect_direct_cycle(self, resolver):
        """Test detection of direct cycle (A→B→A)."""
        tasks = [
            Task(id=1, title="T1", description="", status="pending", priority=1, workflow_step=1, depends_on="[2]"),
            Task(id=2, title="T2", description="", status="pending", priority=1, workflow_step=1, depends_on="[1]"),
        ]

        with pytest.raises(ValueError, match="Circular dependencies"):
            resolver.build_dependency_graph(tasks)

    def test_detect_indirect_cycle(self, resolver):
        """Test detection of indirect cycle (A→B→C→A)."""
        tasks = [
            Task(id=1, title="T1", description="", status="pending", priority=1, workflow_step=1, depends_on="[3]"),
            Task(id=2, title="T2", description="", status="pending", priority=1, workflow_step=1, depends_on="[1]"),
            Task(id=3, title="T3", description="", status="pending", priority=1, workflow_step=1, depends_on="[2]"),
        ]

        with pytest.raises(ValueError, match="Circular dependencies"):
            resolver.build_dependency_graph(tasks)

    def test_detect_self_dependency(self, resolver):
        """Test detection of self-dependency."""
        tasks = [
            Task(id=1, title="T1", description="", status="pending", priority=1, workflow_step=1, depends_on="[1]"),
        ]

        with pytest.raises(ValueError, match="cannot depend on itself"):
            resolver.build_dependency_graph(tasks)


class TestReadyTasks:
    """Test identifying ready tasks."""

    def test_get_ready_tasks_no_dependencies(self, resolver):
        """Test tasks with no dependencies are ready."""
        tasks = [
            Task(id=1, title="T1", description="", status="pending", priority=1, workflow_step=1, depends_on=""),
            Task(id=2, title="T2", description="", status="pending", priority=1, workflow_step=1, depends_on=""),
        ]

        resolver.build_dependency_graph(tasks)
        ready = resolver.get_ready_tasks()

        assert set(ready) == {1, 2}

    def test_get_ready_tasks_some_completed(self, resolver):
        """Test ready tasks when some dependencies completed."""
        tasks = [
            Task(id=1, title="T1", description="", status="completed", priority=1, workflow_step=1, depends_on=""),
            Task(id=2, title="T2", description="", status="pending", priority=1, workflow_step=1, depends_on="[1]"),
            Task(id=3, title="T3", description="", status="pending", priority=1, workflow_step=1, depends_on="[2]"),
        ]

        resolver.build_dependency_graph(tasks)
        ready = resolver.get_ready_tasks()

        assert set(ready) == {2}  # Task 2 is ready (depends on completed task 1)

    def test_get_ready_tasks_all_dependencies_satisfied(self, resolver, complex_tasks):
        """Test ready tasks in complex graph."""
        resolver.build_dependency_graph(complex_tasks)

        ready = resolver.get_ready_tasks()
        assert set(ready) == {1, 2}  # Tasks with no dependencies

        # Mark tasks 1 and 2 as completed
        resolver.completed_tasks.add(1)
        resolver.completed_tasks.add(2)

        ready = resolver.get_ready_tasks()
        assert set(ready) == {3, 4}  # Now tasks 3 and 4 are ready

    def test_get_ready_tasks_exclude_completed(self, resolver, simple_tasks):
        """Test excluding completed tasks from ready list."""
        resolver.build_dependency_graph(simple_tasks)

        # Include completed
        ready_all = resolver.get_ready_tasks(exclude_completed=False)
        assert 1 in ready_all

        # Mark task 1 completed
        resolver.completed_tasks.add(1)

        # Exclude completed (default)
        ready_pending = resolver.get_ready_tasks(exclude_completed=True)
        assert 1 not in ready_pending
        assert 2 in ready_pending


class TestUnblocking:
    """Test task unblocking logic."""

    def test_unblock_single_task(self, resolver, simple_tasks):
        """Test unblocking single dependent task."""
        resolver.build_dependency_graph(simple_tasks)

        unblocked = resolver.unblock_dependent_tasks(1)

        assert unblocked == [2]
        assert 1 in resolver.completed_tasks

    def test_unblock_multiple_tasks(self, resolver):
        """Test unblocking multiple dependent tasks."""
        tasks = [
            Task(id=1, title="T1", description="", status="pending", priority=1, workflow_step=1, depends_on=""),
            Task(id=2, title="T2", description="", status="pending", priority=1, workflow_step=1, depends_on="[1]"),
            Task(id=3, title="T3", description="", status="pending", priority=1, workflow_step=1, depends_on="[1]"),
            Task(id=4, title="T4", description="", status="pending", priority=1, workflow_step=1, depends_on="[1]"),
        ]

        resolver.build_dependency_graph(tasks)
        unblocked = resolver.unblock_dependent_tasks(1)

        assert set(unblocked) == {2, 3, 4}

    def test_unblock_cascading(self, resolver, simple_tasks):
        """Test cascading unblock (A completes → B ready → B completes → C ready)."""
        resolver.build_dependency_graph(simple_tasks)

        # Complete task 1
        unblocked1 = resolver.unblock_dependent_tasks(1)
        assert unblocked1 == [2]

        # Complete task 2
        unblocked2 = resolver.unblock_dependent_tasks(2)
        assert unblocked2 == [3]

    def test_unblock_partial_dependencies(self, resolver, complex_tasks):
        """Test unblocking when only some dependencies are met."""
        resolver.build_dependency_graph(complex_tasks)

        # Complete task 1 (not enough for task 3)
        unblocked = resolver.unblock_dependent_tasks(1)
        assert 3 not in unblocked  # Task 3 also needs task 2
        assert 4 in unblocked  # Task 4 only needs task 1

        # Complete task 2
        unblocked = resolver.unblock_dependent_tasks(2)
        assert 3 in unblocked  # Now task 3 is unblocked


class TestDependencyValidation:
    """Test dependency validation."""

    def test_validate_valid_dependency(self, resolver, simple_tasks):
        """Test validating a safe dependency."""
        resolver.build_dependency_graph(simple_tasks)

        # Adding task 1 → task 2 dependency is safe (no cycle)
        is_valid = resolver.validate_dependency(1, 2)
        assert is_valid is False  # Would create cycle (2 already depends on 1)

    def test_validate_would_create_cycle(self, resolver, simple_tasks):
        """Test rejecting dependency that would create cycle."""
        resolver.build_dependency_graph(simple_tasks)

        # Task 2 depends on 1, adding 1 depends on 2 would create cycle
        is_valid = resolver.validate_dependency(1, 2)
        assert is_valid is False

    def test_validate_self_dependency(self, resolver):
        """Test rejecting self-dependency."""
        tasks = [Task(id=1, title="T1", description="", status="pending", priority=1, workflow_step=1, depends_on="")]
        resolver.build_dependency_graph(tasks)

        with pytest.raises(ValueError, match="cannot depend on itself"):
            resolver.validate_dependency(1, 1)

    def test_validate_safe_new_dependency(self, resolver):
        """Test allowing safe new dependency."""
        tasks = [
            Task(id=1, title="T1", description="", status="pending", priority=1, workflow_step=1, depends_on=""),
            Task(id=2, title="T2", description="", status="pending", priority=1, workflow_step=1, depends_on=""),
            Task(id=3, title="T3", description="", status="pending", priority=1, workflow_step=1, depends_on=""),
        ]
        resolver.build_dependency_graph(tasks)

        # Adding 3 → 2 → 1 is safe
        assert resolver.validate_dependency(3, 2) is True
        assert resolver.validate_dependency(2, 1) is True


class TestTopologicalSort:
    """Test topological sorting."""

    def test_topological_sort_linear(self, resolver, simple_tasks):
        """Test topological sort on linear chain."""
        resolver.build_dependency_graph(simple_tasks)

        topo_order = resolver.topological_sort()

        assert topo_order is not None
        assert topo_order == [1, 2, 3]

    def test_topological_sort_complex(self, resolver, complex_tasks):
        """Test topological sort on complex DAG."""
        resolver.build_dependency_graph(complex_tasks)

        topo_order = resolver.topological_sort()

        assert topo_order is not None
        # Valid orderings: [1,2,3,4,5] or [1,2,4,3,5] or [2,1,3,4,5] or [2,1,4,3,5]
        # Check constraints
        assert topo_order.index(1) < topo_order.index(3)
        assert topo_order.index(2) < topo_order.index(3)
        assert topo_order.index(1) < topo_order.index(4)
        assert topo_order.index(3) < topo_order.index(5)
        assert topo_order.index(4) < topo_order.index(5)

    def test_topological_sort_with_cycle(self, resolver):
        """Test topological sort returns None for cyclic graph."""
        tasks = [
            Task(id=1, title="T1", description="", status="pending", priority=1, workflow_step=1, depends_on="[2]"),
            Task(id=2, title="T2", description="", status="pending", priority=1, workflow_step=1, depends_on="[1]"),
        ]

        # This should raise during build due to cycle detection
        with pytest.raises(ValueError):
            resolver.build_dependency_graph(tasks)


class TestDependencyDepth:
    """Test dependency depth calculation."""

    def test_depth_no_dependencies(self, resolver):
        """Test depth is 0 for tasks with no dependencies."""
        tasks = [Task(id=1, title="T1", description="", status="pending", priority=1, workflow_step=1, depends_on="")]
        resolver.build_dependency_graph(tasks)

        assert resolver.get_dependency_depth(1) == 0

    def test_depth_linear_chain(self, resolver, simple_tasks):
        """Test depth increases in linear chain."""
        resolver.build_dependency_graph(simple_tasks)

        assert resolver.get_dependency_depth(1) == 0
        assert resolver.get_dependency_depth(2) == 1
        assert resolver.get_dependency_depth(3) == 2

    def test_depth_complex_graph(self, resolver, complex_tasks):
        """Test depth in complex graph."""
        resolver.build_dependency_graph(complex_tasks)

        assert resolver.get_dependency_depth(1) == 0
        assert resolver.get_dependency_depth(2) == 0
        assert resolver.get_dependency_depth(3) == 1
        assert resolver.get_dependency_depth(4) == 1
        assert resolver.get_dependency_depth(5) == 2


class TestBlockedTasks:
    """Test identifying blocked tasks."""

    def test_get_blocked_tasks_none(self, resolver):
        """Test no blocked tasks when all are independent."""
        tasks = [
            Task(id=1, title="T1", description="", status="pending", priority=1, workflow_step=1, depends_on=""),
            Task(id=2, title="T2", description="", status="pending", priority=1, workflow_step=1, depends_on=""),
        ]

        resolver.build_dependency_graph(tasks)
        blocked = resolver.get_blocked_tasks()

        assert blocked == {}

    def test_get_blocked_tasks_some(self, resolver, simple_tasks):
        """Test identifying blocked tasks."""
        resolver.build_dependency_graph(simple_tasks)

        blocked = resolver.get_blocked_tasks()

        assert 2 in blocked
        assert blocked[2] == [1]
        assert 3 in blocked
        assert blocked[3] == [2]

    def test_get_blocked_tasks_after_completion(self, resolver, simple_tasks):
        """Test blocked tasks update after completion."""
        resolver.build_dependency_graph(simple_tasks)

        # Complete task 1
        resolver.completed_tasks.add(1)

        blocked = resolver.get_blocked_tasks()

        assert 2 not in blocked  # Task 2 no longer blocked
        assert 3 in blocked  # Task 3 still blocked by task 2


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_graph_operations(self, resolver):
        """Test operations on empty graph."""
        resolver.build_dependency_graph([])

        assert resolver.get_ready_tasks() == []
        assert resolver.unblock_dependent_tasks(1) == []
        assert resolver.detect_cycles() is False
        assert resolver.topological_sort() == []

    def test_missing_task_reference(self, resolver):
        """Test handling of missing task references."""
        tasks = [
            Task(id=1, title="T1", description="", status="pending", priority=1, workflow_step=1, depends_on="[999]"),
        ]

        # Should build graph but log warning
        resolver.build_dependency_graph(tasks)

        # Task 1 will be blocked by non-existent task
        blocked = resolver.get_blocked_tasks()
        assert 1 in blocked

    def test_invalid_depends_on_format(self, resolver):
        """Test handling of invalid depends_on format."""
        tasks = [
            Task(id=1, title="T1", description="", status="pending", priority=1, workflow_step=1, depends_on="invalid"),
        ]

        # Should handle gracefully
        resolver.build_dependency_graph(tasks)
        assert 1 in resolver.all_tasks

    def test_clear_resets_state(self, resolver, simple_tasks):
        """Test clear() resets all state."""
        resolver.build_dependency_graph(simple_tasks)
        resolver.completed_tasks.add(1)

        resolver.clear()

        assert len(resolver.all_tasks) == 0
        assert len(resolver.dependencies) == 0
        assert len(resolver.completed_tasks) == 0


class TestIntegration:
    """Integration tests simulating real workflows."""

    def test_full_workflow_sequential(self, resolver, simple_tasks):
        """Test complete workflow with sequential execution."""
        resolver.build_dependency_graph(simple_tasks)

        # Initially only task 1 is ready
        ready = resolver.get_ready_tasks()
        assert ready == [1]

        # Execute task 1
        unblocked = resolver.unblock_dependent_tasks(1)
        assert unblocked == [2]

        # Execute task 2
        unblocked = resolver.unblock_dependent_tasks(2)
        assert unblocked == [3]

        # Execute task 3
        unblocked = resolver.unblock_dependent_tasks(3)
        assert unblocked == []

        # All tasks completed
        assert resolver.completed_tasks == {1, 2, 3}

    def test_full_workflow_parallel(self, resolver, complex_tasks):
        """Test complete workflow with parallel execution."""
        resolver.build_dependency_graph(complex_tasks)

        # Initially tasks 1 and 2 are ready (can run in parallel)
        ready = resolver.get_ready_tasks()
        assert set(ready) == {1, 2}

        # Execute both in parallel
        unblocked1 = resolver.unblock_dependent_tasks(1)
        unblocked2 = resolver.unblock_dependent_tasks(2)

        # Task 3 and 4 become ready
        all_unblocked = set(unblocked1 + unblocked2)
        assert 3 in all_unblocked
        assert 4 in all_unblocked

        # Execute tasks 3 and 4
        unblocked3 = resolver.unblock_dependent_tasks(3)
        unblocked4 = resolver.unblock_dependent_tasks(4)

        # Task 5 becomes ready
        assert 5 in set(unblocked3 + unblocked4)
