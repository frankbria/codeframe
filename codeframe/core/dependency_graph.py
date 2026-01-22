"""Task dependency graph analysis for batch execution.

Provides DAG construction, cycle detection, topological sorting, and
execution group generation for parallel task execution.

This module is headless - no FastAPI or HTTP dependencies.
"""

from dataclasses import dataclass
from typing import Optional

from codeframe.core.workspace import Workspace
from codeframe.core import tasks as task_module


class CycleDetectedError(Exception):
    """Raised when a circular dependency is detected in the task graph."""

    def __init__(self, cycle: list[str]):
        self.cycle = cycle
        cycle_str = " -> ".join(cycle)
        super().__init__(f"Circular dependency detected: {cycle_str}")


@dataclass
class ExecutionPlan:
    """Represents an execution plan for a set of tasks.

    Attributes:
        groups: List of task ID groups. Tasks within the same group can
                run in parallel. Groups must be executed sequentially.
        task_order: Flat list of task IDs in topological order.
        graph: Dict mapping task_id -> list of task_ids it depends on.
    """

    groups: list[list[str]]
    task_order: list[str]
    graph: dict[str, list[str]]

    @property
    def total_tasks(self) -> int:
        """Total number of tasks in the plan."""
        return len(self.task_order)

    @property
    def num_groups(self) -> int:
        """Number of execution groups."""
        return len(self.groups)

    def can_run_parallel(self) -> bool:
        """Check if any groups have more than one task (parallelizable)."""
        return any(len(group) > 1 for group in self.groups)


def build_graph(
    workspace: Workspace,
    task_ids: list[str],
) -> dict[str, list[str]]:
    """Build a dependency graph for the given tasks.

    Args:
        workspace: Workspace containing the tasks
        task_ids: List of task IDs to include in the graph

    Returns:
        Dict mapping task_id -> list of dependency task_ids

    Note:
        Only includes dependencies that are within the provided task_ids.
        External dependencies are filtered out.
    """
    task_id_set = set(task_ids)
    graph: dict[str, list[str]] = {}

    for task_id in task_ids:
        task = task_module.get(workspace, task_id)
        if task:
            # Only include dependencies that are in our task set
            deps = [d for d in task.depends_on if d in task_id_set]
            graph[task_id] = deps
        else:
            graph[task_id] = []

    return graph


def detect_cycle(graph: dict[str, list[str]]) -> Optional[list[str]]:
    """Detect if the graph contains a cycle.

    Args:
        graph: Dependency graph (task_id -> list of dependencies)

    Returns:
        List of task IDs forming a cycle, or None if no cycle exists.
        The cycle list starts and ends with the same task ID.
    """
    # States: 0 = unvisited, 1 = visiting, 2 = visited
    state: dict[str, int] = {node: 0 for node in graph}
    parent: dict[str, Optional[str]] = {node: None for node in graph}

    def dfs(node: str, path: list[str]) -> Optional[list[str]]:
        state[node] = 1  # visiting
        path.append(node)

        for dep in graph.get(node, []):
            if dep not in state:
                continue  # dependency not in our graph

            if state[dep] == 1:  # back edge - cycle found
                # Find where the cycle starts
                cycle_start = path.index(dep)
                cycle = path[cycle_start:] + [dep]
                return cycle

            if state[dep] == 0:  # unvisited
                parent[dep] = node
                result = dfs(dep, path)
                if result:
                    return result

        state[node] = 2  # visited
        path.pop()
        return None

    for node in graph:
        if state[node] == 0:
            cycle = dfs(node, [])
            if cycle:
                return cycle

    return None


def topological_sort(graph: dict[str, list[str]]) -> list[str]:
    """Perform topological sort on the dependency graph.

    Args:
        graph: Dependency graph (task_id -> list of dependencies)

    Returns:
        List of task IDs in topological order (dependencies first).

    Raises:
        CycleDetectedError: If the graph contains a cycle.
    """
    cycle = detect_cycle(graph)
    if cycle:
        raise CycleDetectedError(cycle)

    # Kahn's algorithm for topological sort
    # graph[node] = deps means node depends on deps
    # So deps must come before node
    # in_degree[node] = number of dependencies that node has
    in_degree = {node: len(graph.get(node, [])) for node in graph}

    # Start with nodes that have no dependencies
    queue = [node for node in graph if in_degree[node] == 0]
    result = []

    while queue:
        # Take a node with no remaining dependencies
        node = queue.pop(0)
        result.append(node)

        # For each node that depends on this node, reduce its in_degree
        for other_node in graph:
            if node in graph.get(other_node, []):
                in_degree[other_node] -= 1
                if in_degree[other_node] == 0:
                    queue.append(other_node)

    if len(result) != len(graph):
        # This shouldn't happen if detect_cycle works correctly
        raise CycleDetectedError(["unknown cycle"])

    return result


def group_by_level(graph: dict[str, list[str]]) -> list[list[str]]:
    """Group tasks by dependency level for parallel execution.

    Tasks at the same level have no dependencies on each other and
    can be executed in parallel. Levels must be executed sequentially.

    Args:
        graph: Dependency graph (task_id -> list of dependencies)

    Returns:
        List of groups, where each group contains task IDs that can
        run in parallel. Groups are ordered by execution order.

    Raises:
        CycleDetectedError: If the graph contains a cycle.
    """
    cycle = detect_cycle(graph)
    if cycle:
        raise CycleDetectedError(cycle)

    if not graph:
        return []

    # Calculate the level of each node (longest path from a root)
    levels: dict[str, int] = {}

    def calculate_level(node: str) -> int:
        if node in levels:
            return levels[node]

        deps = graph.get(node, [])
        if not deps:
            levels[node] = 0
        else:
            # Level is 1 + max level of dependencies
            max_dep_level = max(
                calculate_level(dep) for dep in deps if dep in graph
            )
            levels[node] = max_dep_level + 1

        return levels[node]

    for node in graph:
        calculate_level(node)

    # Group by level
    max_level = max(levels.values()) if levels else 0
    groups: list[list[str]] = [[] for _ in range(max_level + 1)]

    for node, level in levels.items():
        groups[level].append(node)

    # Remove empty groups and return
    return [g for g in groups if g]


def create_execution_plan(
    workspace: Workspace,
    task_ids: list[str],
) -> ExecutionPlan:
    """Create an execution plan for the given tasks.

    Analyzes task dependencies to produce an execution plan with:
    - Topologically sorted task order
    - Parallel execution groups (tasks that can run concurrently)

    Args:
        workspace: Workspace containing the tasks
        task_ids: List of task IDs to plan execution for

    Returns:
        ExecutionPlan with groups, task_order, and graph

    Raises:
        CycleDetectedError: If there's a circular dependency
    """
    if not task_ids:
        return ExecutionPlan(groups=[], task_order=[], graph={})

    graph = build_graph(workspace, task_ids)
    task_order = topological_sort(graph)
    groups = group_by_level(graph)

    return ExecutionPlan(
        groups=groups,
        task_order=task_order,
        graph=graph,
    )


def validate_dependencies(
    workspace: Workspace,
    task_ids: list[str],
) -> tuple[bool, Optional[str]]:
    """Validate that the task dependencies form a valid DAG.

    Args:
        workspace: Workspace containing the tasks
        task_ids: List of task IDs to validate

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is None.
    """
    try:
        graph = build_graph(workspace, task_ids)
        cycle = detect_cycle(graph)
        if cycle:
            cycle_str = " -> ".join(cycle)
            return False, f"Circular dependency: {cycle_str}"
        return True, None
    except Exception as e:
        return False, str(e)
