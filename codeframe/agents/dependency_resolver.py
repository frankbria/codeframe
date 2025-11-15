"""
DAG-based Task Dependency Resolver (Sprint 4: cf-50).

This module provides dependency resolution for multi-agent task coordination,
ensuring tasks are executed in correct order based on their dependencies.
"""

import logging
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict, deque

from codeframe.core.models import Task

logger = logging.getLogger(__name__)


class DependencyResolver:
    """
    DAG-based dependency resolver for task coordination.

    Capabilities:
    - Build directed acyclic graph (DAG) from task dependencies
    - Identify ready tasks (all dependencies satisfied)
    - Find newly unblocked tasks after completion
    - Detect circular dependencies
    - Validate dependencies before adding
    - Suggest execution order via topological sort
    """

    def __init__(self):
        """Initialize dependency resolver."""
        # Adjacency list: task_id -> set of task_ids it depends on
        self.dependencies: Dict[int, Set[int]] = defaultdict(set)

        # Reverse adjacency list: task_id -> set of task_ids that depend on it
        self.dependents: Dict[int, Set[int]] = defaultdict(set)

        # Track completed tasks
        self.completed_tasks: Set[int] = set()

        # Track all known tasks
        self.all_tasks: Set[int] = set()

    def build_dependency_graph(self, tasks: List[Task]) -> None:
        """
        Build dependency graph from task list.

        Args:
            tasks: List of tasks with dependency information

        Raises:
            ValueError: If circular dependencies detected
        """
        # Clear existing graph
        self.dependencies.clear()
        self.dependents.clear()
        self.completed_tasks.clear()
        self.all_tasks.clear()

        # First pass: register all tasks
        for task in tasks:
            self.all_tasks.add(task.id)
            if task.status == "completed":
                self.completed_tasks.add(task.id)

        # Second pass: build dependency edges
        for task in tasks:
            task_id = task.id

            # Parse depends_on field (JSON array or empty string)
            if task.depends_on and task.depends_on.strip():
                # Handle JSON array format: "[1, 2, 3]" or comma-separated "1,2,3"
                depends_on_str = task.depends_on.strip()

                if depends_on_str.startswith("[") and depends_on_str.endswith("]"):
                    # JSON array format
                    import json

                    try:
                        dep_ids = json.loads(depends_on_str)
                    except json.JSONDecodeError:
                        logger.warning(
                            f"Invalid JSON in depends_on for task {task_id}: {depends_on_str}"
                        )
                        dep_ids = []
                else:
                    # Comma-separated format
                    try:
                        dep_ids = [int(x.strip()) for x in depends_on_str.split(",") if x.strip()]
                    except ValueError:
                        logger.warning(
                            f"Invalid depends_on format for task {task_id}: {depends_on_str}"
                        )
                        dep_ids = []

                for dep_id in dep_ids:
                    if dep_id == task_id:
                        raise ValueError(
                            f"Task {task_id} cannot depend on itself (self-dependency)"
                        )

                    if dep_id not in self.all_tasks:
                        logger.warning(
                            f"Task {task_id} depends on unknown task {dep_id}. "
                            "Dependency will be tracked but may cause blocking."
                        )

                    self.dependencies[task_id].add(dep_id)
                    self.dependents[dep_id].add(task_id)

        # Validate no cycles
        if self.detect_cycles():
            cycles = self._find_cycle_details()
            raise ValueError(f"Circular dependencies detected: {cycles}")

        logger.info(
            f"Built dependency graph: {len(self.all_tasks)} tasks, "
            f"{sum(len(deps) for deps in self.dependencies.values())} dependencies"
        )

    def get_ready_tasks(self, exclude_completed: bool = True) -> List[int]:
        """
        Get tasks that are ready to execute (all dependencies satisfied).

        Args:
            exclude_completed: If True, exclude already completed tasks

        Returns:
            List of task IDs ready for execution
        """
        ready = []

        for task_id in self.all_tasks:
            # Skip completed tasks if requested
            if exclude_completed and task_id in self.completed_tasks:
                continue

            # Check if all dependencies are satisfied
            deps = self.dependencies.get(task_id, set())

            if not deps:
                # No dependencies - always ready
                ready.append(task_id)
            elif deps.issubset(self.completed_tasks):
                # All dependencies completed
                ready.append(task_id)

        return sorted(ready)

    def unblock_dependent_tasks(self, completed_task_id: int) -> List[int]:
        """
        Find tasks that become unblocked after a task completes.

        Args:
            completed_task_id: ID of task that just completed

        Returns:
            List of task IDs that are now unblocked
        """
        # Mark task as completed
        self.completed_tasks.add(completed_task_id)

        # Find tasks that depend on this task
        dependent_ids = self.dependents.get(completed_task_id, set())

        unblocked = []
        for dep_id in dependent_ids:
            # Check if all dependencies are now satisfied
            all_deps = self.dependencies.get(dep_id, set())
            if all_deps.issubset(self.completed_tasks):
                unblocked.append(dep_id)

        logger.debug(
            f"Task {completed_task_id} completion unblocked {len(unblocked)} tasks: {unblocked}"
        )

        return sorted(unblocked)

    def detect_cycles(self) -> bool:
        """
        Detect if dependency graph contains cycles using DFS.

        Returns:
            True if cycles detected, False otherwise
        """
        # Track visited nodes and nodes in current DFS path
        visited = set()
        rec_stack = set()

        def has_cycle(node: int) -> bool:
            """DFS helper to detect cycle from node."""
            visited.add(node)
            rec_stack.add(node)

            # Check all dependencies of this node
            for dep in self.dependencies.get(node, set()):
                if dep not in visited:
                    if has_cycle(dep):
                        return True
                elif dep in rec_stack:
                    # Found a back edge (cycle)
                    return True

            rec_stack.remove(node)
            return False

        # Check all nodes
        for task_id in self.all_tasks:
            if task_id not in visited:
                if has_cycle(task_id):
                    return True

        return False

    def validate_dependency(self, task_id: int, depends_on_id: int) -> bool:
        """
        Validate adding a dependency would not create a cycle.

        Args:
            task_id: Task that will depend on another
            depends_on_id: Task to depend on

        Returns:
            True if dependency is valid (no cycle), False if would create cycle

        Raises:
            ValueError: If self-dependency attempted
        """
        if task_id == depends_on_id:
            raise ValueError(f"Task {task_id} cannot depend on itself (self-dependency)")

        # Temporarily add the dependency
        self.dependencies[task_id].add(depends_on_id)
        self.dependents[depends_on_id].add(task_id)

        # Check for cycles
        has_cycle = self.detect_cycles()

        # Remove temporary dependency
        self.dependencies[task_id].discard(depends_on_id)
        self.dependents[depends_on_id].discard(task_id)

        if has_cycle:
            logger.warning(
                f"Cannot add dependency: task {task_id} → {depends_on_id} " "would create a cycle"
            )
            return False

        return True

    def topological_sort(self) -> Optional[List[int]]:
        """
        Compute topological ordering of tasks using Kahn's algorithm.

        Returns:
            List of task IDs in topological order, or None if cycle exists
        """
        # Compute in-degree for each task
        in_degree = {
            task_id: len(self.dependencies.get(task_id, set())) for task_id in self.all_tasks
        }

        # Queue of tasks with no dependencies
        queue = deque([task_id for task_id in self.all_tasks if in_degree[task_id] == 0])

        result = []

        while queue:
            # Process task with no remaining dependencies
            task_id = queue.popleft()
            result.append(task_id)

            # Reduce in-degree of dependent tasks
            for dependent_id in self.dependents.get(task_id, set()):
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    queue.append(dependent_id)

        # If we processed all tasks, we have a valid topological order
        if len(result) == len(self.all_tasks):
            return result
        else:
            # Cycle detected
            logger.error("Cannot perform topological sort: cycle detected")
            return None

    def get_dependency_depth(self, task_id: int) -> int:
        """
        Get maximum dependency depth for a task (for priority calculation).

        Args:
            task_id: Task ID to analyze

        Returns:
            Maximum depth (0 for no dependencies, N for N levels deep)
        """
        if task_id not in self.all_tasks:
            return 0

        # Use BFS to find maximum depth
        deps = self.dependencies.get(task_id, set())
        if not deps:
            return 0

        max_depth = 0
        for dep_id in deps:
            depth = 1 + self.get_dependency_depth(dep_id)
            max_depth = max(max_depth, depth)

        return max_depth

    def get_blocked_tasks(self) -> Dict[int, List[int]]:
        """
        Get all blocked tasks and what they're blocked by.

        Returns:
            Dict mapping task_id to list of blocking task_ids
        """
        blocked = {}

        for task_id in self.all_tasks:
            if task_id in self.completed_tasks:
                continue

            deps = self.dependencies.get(task_id, set())
            if deps:
                # Get incomplete dependencies
                incomplete_deps = deps - self.completed_tasks
                if incomplete_deps:
                    blocked[task_id] = sorted(incomplete_deps)

        return blocked

    def _find_cycle_details(self) -> str:
        """
        Find and describe a cycle in the graph (for error messages).

        Returns:
            String describing the cycle
        """
        visited = set()
        rec_stack = []

        def find_cycle_from(node: int) -> Optional[str]:
            """DFS to find cycle."""
            visited.add(node)
            rec_stack.append(node)

            for dep in self.dependencies.get(node, set()):
                if dep not in visited:
                    result = find_cycle_from(dep)
                    if result:
                        return result
                elif dep in rec_stack:
                    # Found cycle
                    cycle_start = rec_stack.index(dep)
                    cycle = rec_stack[cycle_start:] + [dep]
                    return " → ".join(map(str, cycle))

            rec_stack.pop()
            return None

        for task_id in self.all_tasks:
            if task_id not in visited:
                cycle = find_cycle_from(task_id)
                if cycle:
                    return cycle

        return "Unknown cycle"

    def clear(self) -> None:
        """Clear all dependency data (for testing/reset)."""
        self.dependencies.clear()
        self.dependents.clear()
        self.completed_tasks.clear()
        self.all_tasks.clear()
