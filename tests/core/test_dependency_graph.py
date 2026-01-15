"""Tests for dependency graph analysis.

Tests DAG construction, cycle detection, topological sorting, and
execution plan generation.
"""

import pytest

from codeframe.core import tasks
from codeframe.core.dependency_graph import (
    CycleDetectedError,
    ExecutionPlan,
    build_graph,
    detect_cycle,
    topological_sort,
    group_by_level,
    create_execution_plan,
    validate_dependencies,
)
from codeframe.core.workspace import create_or_load_workspace


@pytest.fixture
def workspace(tmp_path):
    """Create a test workspace."""
    return create_or_load_workspace(tmp_path)


class TestBuildGraph:
    """Test graph construction from tasks."""

    def test_empty_task_list(self, workspace):
        """Empty task list produces empty graph."""
        graph = build_graph(workspace, [])
        assert graph == {}

    def test_single_task_no_deps(self, workspace):
        """Single task with no dependencies."""
        task = tasks.create(workspace, title="Task A")
        graph = build_graph(workspace, [task.id])
        assert graph == {task.id: []}

    def test_two_tasks_with_dependency(self, workspace):
        """Task B depends on Task A."""
        task_a = tasks.create(workspace, title="Task A")
        task_b = tasks.create(workspace, title="Task B", depends_on=[task_a.id])

        graph = build_graph(workspace, [task_a.id, task_b.id])

        assert graph[task_a.id] == []
        assert graph[task_b.id] == [task_a.id]

    def test_filters_external_dependencies(self, workspace):
        """Dependencies outside task list are filtered."""
        task_a = tasks.create(workspace, title="Task A")
        task_b = tasks.create(workspace, title="Task B", depends_on=[task_a.id])

        # Only include task_b, not task_a
        graph = build_graph(workspace, [task_b.id])

        # task_a dependency should be filtered out
        assert graph[task_b.id] == []


class TestDetectCycle:
    """Test cycle detection in dependency graphs."""

    def test_no_cycle_empty_graph(self):
        """Empty graph has no cycle."""
        assert detect_cycle({}) is None

    def test_no_cycle_single_node(self):
        """Single node with no dependencies has no cycle."""
        assert detect_cycle({"a": []}) is None

    def test_no_cycle_linear(self):
        """Linear chain has no cycle: a -> b -> c"""
        graph = {"a": [], "b": ["a"], "c": ["b"]}
        assert detect_cycle(graph) is None

    def test_no_cycle_diamond(self):
        """Diamond shape has no cycle: d depends on both b and c, both depend on a"""
        graph = {
            "a": [],
            "b": ["a"],
            "c": ["a"],
            "d": ["b", "c"],
        }
        assert detect_cycle(graph) is None

    def test_self_cycle(self):
        """Task depending on itself is a cycle."""
        graph = {"a": ["a"]}
        cycle = detect_cycle(graph)
        assert cycle is not None
        assert "a" in cycle

    def test_two_node_cycle(self):
        """Two nodes in a cycle: a -> b -> a"""
        graph = {"a": ["b"], "b": ["a"]}
        cycle = detect_cycle(graph)
        assert cycle is not None
        assert len(set(cycle)) == 2  # Both a and b in cycle

    def test_three_node_cycle(self):
        """Three nodes in a cycle: a -> b -> c -> a"""
        graph = {"a": ["c"], "b": ["a"], "c": ["b"]}
        cycle = detect_cycle(graph)
        assert cycle is not None


class TestTopologicalSort:
    """Test topological sorting of dependency graph."""

    def test_empty_graph(self):
        """Empty graph produces empty sort."""
        assert topological_sort({}) == []

    def test_single_node(self):
        """Single node returns that node."""
        result = topological_sort({"a": []})
        assert result == ["a"]

    def test_linear_chain(self):
        """Linear chain sorted correctly: c depends on b depends on a."""
        graph = {"a": [], "b": ["a"], "c": ["b"]}
        result = topological_sort(graph)

        # a must come before b, b must come before c
        assert result.index("a") < result.index("b")
        assert result.index("b") < result.index("c")

    def test_diamond(self):
        """Diamond shape sorted correctly."""
        graph = {
            "a": [],
            "b": ["a"],
            "c": ["a"],
            "d": ["b", "c"],
        }
        result = topological_sort(graph)

        # a must come first
        # b and c after a
        # d must come last
        assert result.index("a") < result.index("b")
        assert result.index("a") < result.index("c")
        assert result.index("b") < result.index("d")
        assert result.index("c") < result.index("d")

    def test_raises_on_cycle(self):
        """Raises CycleDetectedError if graph has cycle."""
        graph = {"a": ["b"], "b": ["a"]}
        with pytest.raises(CycleDetectedError) as exc_info:
            topological_sort(graph)
        assert exc_info.value.cycle is not None

    def test_multiple_independent_tasks(self):
        """Independent tasks can be in any order."""
        graph = {"a": [], "b": [], "c": []}
        result = topological_sort(graph)

        assert set(result) == {"a", "b", "c"}
        assert len(result) == 3


class TestGroupByLevel:
    """Test grouping tasks by dependency level."""

    def test_empty_graph(self):
        """Empty graph produces empty groups."""
        assert group_by_level({}) == []

    def test_single_task(self):
        """Single task is one group."""
        result = group_by_level({"a": []})
        assert result == [["a"]]

    def test_independent_tasks(self):
        """Independent tasks are all at level 0."""
        result = group_by_level({"a": [], "b": [], "c": []})
        assert len(result) == 1
        assert set(result[0]) == {"a", "b", "c"}

    def test_linear_chain(self):
        """Linear chain has one task per level."""
        graph = {"a": [], "b": ["a"], "c": ["b"]}
        result = group_by_level(graph)

        assert len(result) == 3
        assert result[0] == ["a"]
        assert result[1] == ["b"]
        assert result[2] == ["c"]

    def test_diamond(self):
        """Diamond has three levels: a, then b+c, then d."""
        graph = {
            "a": [],
            "b": ["a"],
            "c": ["a"],
            "d": ["b", "c"],
        }
        result = group_by_level(graph)

        assert len(result) == 3
        assert result[0] == ["a"]
        assert set(result[1]) == {"b", "c"}
        assert result[2] == ["d"]

    def test_raises_on_cycle(self):
        """Raises CycleDetectedError if graph has cycle."""
        graph = {"a": ["b"], "b": ["a"]}
        with pytest.raises(CycleDetectedError):
            group_by_level(graph)


class TestCreateExecutionPlan:
    """Test execution plan creation."""

    def test_empty_tasks(self, workspace):
        """Empty task list produces empty plan."""
        plan = create_execution_plan(workspace, [])

        assert plan.groups == []
        assert plan.task_order == []
        assert plan.total_tasks == 0
        assert plan.num_groups == 0

    def test_single_task(self, workspace):
        """Single task plan."""
        task = tasks.create(workspace, title="Task A")
        plan = create_execution_plan(workspace, [task.id])

        assert plan.total_tasks == 1
        assert plan.num_groups == 1
        assert plan.task_order == [task.id]
        assert plan.groups == [[task.id]]
        assert not plan.can_run_parallel()

    def test_independent_tasks_can_parallel(self, workspace):
        """Independent tasks can run in parallel."""
        task_a = tasks.create(workspace, title="Task A")
        task_b = tasks.create(workspace, title="Task B")
        task_c = tasks.create(workspace, title="Task C")

        plan = create_execution_plan(workspace, [task_a.id, task_b.id, task_c.id])

        assert plan.total_tasks == 3
        assert plan.num_groups == 1
        assert plan.can_run_parallel()
        assert set(plan.groups[0]) == {task_a.id, task_b.id, task_c.id}

    def test_dependent_tasks_sequential(self, workspace):
        """Dependent tasks must run sequentially."""
        task_a = tasks.create(workspace, title="Task A")
        task_b = tasks.create(workspace, title="Task B", depends_on=[task_a.id])

        plan = create_execution_plan(workspace, [task_a.id, task_b.id])

        assert plan.total_tasks == 2
        assert plan.num_groups == 2
        assert not plan.can_run_parallel()
        assert plan.task_order.index(task_a.id) < plan.task_order.index(task_b.id)

    def test_mixed_parallel_and_sequential(self, workspace):
        """Mixed dependencies produce mixed groups."""
        task_a = tasks.create(workspace, title="Task A")
        task_b = tasks.create(workspace, title="Task B")  # Independent of A
        task_c = tasks.create(workspace, title="Task C", depends_on=[task_a.id, task_b.id])

        plan = create_execution_plan(workspace, [task_a.id, task_b.id, task_c.id])

        assert plan.total_tasks == 3
        assert plan.num_groups == 2
        assert plan.can_run_parallel()

        # First group: a and b (can run in parallel)
        assert set(plan.groups[0]) == {task_a.id, task_b.id}
        # Second group: c (depends on both)
        assert plan.groups[1] == [task_c.id]

    def test_raises_on_cycle(self, workspace):
        """Raises error for circular dependencies."""
        task_a = tasks.create(workspace, title="Task A")
        task_b = tasks.create(workspace, title="Task B", depends_on=[task_a.id])

        # Create cycle by updating task_a to depend on task_b
        tasks.update_depends_on(workspace, task_a.id, [task_b.id])

        with pytest.raises(CycleDetectedError):
            create_execution_plan(workspace, [task_a.id, task_b.id])


class TestValidateDependencies:
    """Test dependency validation."""

    def test_valid_no_deps(self, workspace):
        """Tasks with no dependencies are valid."""
        task_a = tasks.create(workspace, title="Task A")
        task_b = tasks.create(workspace, title="Task B")

        valid, error = validate_dependencies(workspace, [task_a.id, task_b.id])

        assert valid is True
        assert error is None

    def test_valid_linear_deps(self, workspace):
        """Linear dependencies are valid."""
        task_a = tasks.create(workspace, title="Task A")
        task_b = tasks.create(workspace, title="Task B", depends_on=[task_a.id])

        valid, error = validate_dependencies(workspace, [task_a.id, task_b.id])

        assert valid is True
        assert error is None

    def test_invalid_cycle(self, workspace):
        """Circular dependencies are invalid."""
        task_a = tasks.create(workspace, title="Task A")
        task_b = tasks.create(workspace, title="Task B", depends_on=[task_a.id])
        tasks.update_depends_on(workspace, task_a.id, [task_b.id])

        valid, error = validate_dependencies(workspace, [task_a.id, task_b.id])

        assert valid is False
        assert "Circular dependency" in error


class TestExecutionPlan:
    """Test ExecutionPlan dataclass."""

    def test_properties(self):
        """Test ExecutionPlan properties."""
        plan = ExecutionPlan(
            groups=[["a", "b"], ["c"]],
            task_order=["a", "b", "c"],
            graph={"a": [], "b": [], "c": ["a", "b"]},
        )

        assert plan.total_tasks == 3
        assert plan.num_groups == 2
        assert plan.can_run_parallel() is True

    def test_cannot_parallel_linear(self):
        """Linear plan cannot run parallel."""
        plan = ExecutionPlan(
            groups=[["a"], ["b"], ["c"]],
            task_order=["a", "b", "c"],
            graph={"a": [], "b": ["a"], "c": ["b"]},
        )

        assert plan.can_run_parallel() is False
