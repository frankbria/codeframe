"""
DAG-based Task Dependency Resolver (Sprint 4: cf-50).

This module provides dependency resolution for multi-agent task coordination,
ensuring tasks are executed in correct order based on their dependencies.

Enhanced in Phase 2 with:
- Critical path analysis (longest path through DAG)
- Task slack/float calculation
- Parallel execution opportunity identification
- Dependency conflict detection and resolution suggestions
"""

import logging
from typing import Dict, List, Set, Optional
from collections import defaultdict, deque
from dataclasses import dataclass

from codeframe.core.models import Task

logger = logging.getLogger(__name__)


@dataclass
class TaskTiming:
    """Timing information for a task in critical path analysis."""

    earliest_start: float
    earliest_finish: float
    latest_start: float
    latest_finish: float


@dataclass
class CriticalPathResult:
    """Result of critical path calculation."""

    critical_task_ids: List[int]
    total_duration: float
    task_timings: Dict[int, TaskTiming]


@dataclass
class DependencyConflict:
    """Represents a detected dependency conflict or bottleneck."""

    task_id: int
    conflict_type: str  # "bottleneck", "long_chain", "high_risk_multiplier"
    severity: str  # "critical", "high", "medium"
    recommendation: str
    impact_analysis: str


@dataclass
class ResolutionSuggestion:
    """Suggested resolution for a dependency conflict."""

    suggestion_type: str  # "split_task", "reorder", "prioritize"
    description: str
    affected_task_ids: List[int]
    expected_improvement: str


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
            # Handle both v2 (TaskStatus enum) and legacy (string) status
            status = task.status.value if hasattr(task.status, 'value') else str(task.status)
            if status.upper() in ("DONE", "COMPLETED"):
                self.completed_tasks.add(task.id)

        # Second pass: build dependency edges
        for task in tasks:
            task_id = task.id

            # Parse depends_on field - supports both:
            # - List format (v2): [task_id_1, task_id_2]
            # - String format (legacy): "[1, 2, 3]" or "1,2,3"
            dep_ids = []

            if task.depends_on:
                if isinstance(task.depends_on, list):
                    # v2 format: already a list
                    dep_ids = task.depends_on
                elif isinstance(task.depends_on, str) and task.depends_on.strip():
                    # Legacy string format
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

    # ========== Phase 2: Critical Path Analysis ==========

    def calculate_critical_path(
        self, task_durations: Dict[int, float]
    ) -> CriticalPathResult:
        """
        Calculate the critical path through the task dependency graph.

        Uses forward and backward passes to compute earliest/latest times
        and identifies tasks with zero slack (critical path).

        Args:
            task_durations: Dict mapping task_id to duration in hours.
                           Missing tasks default to 0 duration.

        Returns:
            CriticalPathResult with critical task IDs, total duration, and timings
        """
        # Get topological order
        topo_order = self.topological_sort()
        if not topo_order:
            # If cycle detected, return empty result
            return CriticalPathResult(
                critical_task_ids=[],
                total_duration=0.0,
                task_timings={},
            )

        # Initialize timing data
        task_timings: Dict[int, TaskTiming] = {}

        # Forward pass: compute earliest start/finish times
        earliest_start: Dict[int, float] = {}
        earliest_finish: Dict[int, float] = {}

        for task_id in topo_order:
            duration = task_durations.get(task_id, 0.0)
            deps = self.dependencies.get(task_id, set())

            if not deps:
                # No dependencies - starts at time 0
                earliest_start[task_id] = 0.0
            else:
                # Earliest start is max of all dependency finish times
                earliest_start[task_id] = max(
                    earliest_finish.get(dep_id, 0.0) for dep_id in deps
                )

            earliest_finish[task_id] = earliest_start[task_id] + duration

        # Project end time is the maximum earliest finish
        project_duration = max(earliest_finish.values()) if earliest_finish else 0.0

        # Backward pass: compute latest start/finish times
        latest_finish: Dict[int, float] = {}
        latest_start: Dict[int, float] = {}

        for task_id in reversed(topo_order):
            duration = task_durations.get(task_id, 0.0)
            dependents = self.dependents.get(task_id, set())

            if not dependents:
                # No dependents - must finish by project end
                latest_finish[task_id] = project_duration
            else:
                # Latest finish is min of all dependent start times
                latest_finish[task_id] = min(
                    latest_start.get(dep_id, project_duration) for dep_id in dependents
                )

            latest_start[task_id] = latest_finish[task_id] - duration

        # Build timing objects and identify critical path (zero slack)
        critical_task_ids = []

        for task_id in self.all_tasks:
            timing = TaskTiming(
                earliest_start=earliest_start.get(task_id, 0.0),
                earliest_finish=earliest_finish.get(task_id, 0.0),
                latest_start=latest_start.get(task_id, 0.0),
                latest_finish=latest_finish.get(task_id, 0.0),
            )
            task_timings[task_id] = timing

            # Task is on critical path if slack is zero
            slack = timing.latest_start - timing.earliest_start
            if abs(slack) < 0.001:  # Float comparison tolerance
                critical_task_ids.append(task_id)

        return CriticalPathResult(
            critical_task_ids=sorted(critical_task_ids),
            total_duration=project_duration,
            task_timings=task_timings,
        )

    def calculate_task_slack(self, task_durations: Dict[int, float]) -> Dict[int, float]:
        """
        Calculate slack/float time for each task.

        Slack = Latest Start - Earliest Start
        Tasks with zero slack are on the critical path.

        Args:
            task_durations: Dict mapping task_id to duration in hours

        Returns:
            Dict mapping task_id to slack time in hours
        """
        result = self.calculate_critical_path(task_durations)

        slack = {}
        for task_id, timing in result.task_timings.items():
            slack[task_id] = timing.latest_start - timing.earliest_start

        return slack

    def identify_parallel_opportunities(self) -> Dict[int, List[int]]:
        """
        Identify tasks that can execute in parallel (execution waves).

        Groups tasks by their dependency level - tasks in the same wave
        have no dependencies on each other and can run concurrently.

        Returns:
            Dict mapping wave number (0, 1, 2...) to list of task IDs
        """
        # Use topological sort with level tracking
        in_degree = {
            task_id: len(self.dependencies.get(task_id, set()))
            for task_id in self.all_tasks
        }

        # Track which level each task belongs to
        task_level: Dict[int, int] = {}

        # Start with tasks that have no dependencies (level 0)
        current_level = 0
        queue = deque([task_id for task_id in self.all_tasks if in_degree[task_id] == 0])

        while queue:
            # Process all tasks at current level
            level_size = len(queue)

            for _ in range(level_size):
                task_id = queue.popleft()
                task_level[task_id] = current_level

                # Add dependents to next level if their in-degree becomes 0
                for dependent_id in self.dependents.get(task_id, set()):
                    in_degree[dependent_id] -= 1
                    if in_degree[dependent_id] == 0:
                        queue.append(dependent_id)

            current_level += 1

        # Group tasks by level
        waves: Dict[int, List[int]] = defaultdict(list)
        for task_id, level in task_level.items():
            waves[level].append(task_id)

        # Sort task IDs within each wave
        return {level: sorted(tasks) for level, tasks in waves.items()}

    # ========== Phase 2: Conflict Detection ==========

    def detect_dependency_conflicts(
        self, task_durations: Dict[int, float]
    ) -> List[DependencyConflict]:
        """
        Detect dependency conflicts, bottlenecks, and risk patterns.

        Identifies:
        - Bottleneck tasks (many dependents, high impact on critical path)
        - Long dependency chains (> 5 tasks in sequence)
        - High-risk multipliers (high complexity + many dependents)

        Args:
            task_durations: Dict mapping task_id to duration in hours

        Returns:
            List of DependencyConflict objects with severity and recommendations
        """
        conflicts: List[DependencyConflict] = []

        # Get critical path info
        cp_result = self.calculate_critical_path(task_durations)
        critical_set = set(cp_result.critical_task_ids)

        # Detect bottleneck tasks (3+ dependents)
        bottleneck_threshold = 3
        for task_id in self.all_tasks:
            dependent_count = len(self.dependents.get(task_id, set()))

            if dependent_count >= bottleneck_threshold:
                duration = task_durations.get(task_id, 0.0)
                is_critical = task_id in critical_set

                severity = "critical" if is_critical and duration > 4 else "high" if is_critical else "medium"

                conflicts.append(
                    DependencyConflict(
                        task_id=task_id,
                        conflict_type="bottleneck",
                        severity=severity,
                        recommendation=f"Consider splitting task {task_id} into smaller tasks "
                        f"to reduce blocking impact on {dependent_count} dependent tasks",
                        impact_analysis=f"Task {task_id} blocks {dependent_count} tasks. "
                        f"Duration: {duration}h. On critical path: {is_critical}",
                    )
                )

        # Detect long dependency chains (> 5 tasks)
        chain_threshold = 5
        for task_id in self.all_tasks:
            depth = self.get_dependency_depth(task_id)
            if depth >= chain_threshold:
                conflicts.append(
                    DependencyConflict(
                        task_id=task_id,
                        conflict_type="long_chain",
                        severity="high" if task_id in critical_set else "medium",
                        recommendation=f"Consider parallelizing some tasks in the chain "
                        f"leading to task {task_id}",
                        impact_analysis=f"Task {task_id} has dependency depth of {depth}, "
                        f"creating a long sequential chain",
                    )
                )

        return conflicts

    def suggest_dependency_resolution(
        self, conflicts: List[DependencyConflict]
    ) -> List[ResolutionSuggestion]:
        """
        Generate resolution suggestions for detected conflicts.

        Args:
            conflicts: List of detected dependency conflicts

        Returns:
            List of ResolutionSuggestion objects
        """
        suggestions: List[ResolutionSuggestion] = []

        for conflict in conflicts:
            if conflict.conflict_type == "bottleneck":
                # Suggest task splitting
                suggestions.append(
                    ResolutionSuggestion(
                        suggestion_type="split_task",
                        description=f"Split task {conflict.task_id} into multiple smaller tasks "
                        f"that can be worked on independently",
                        affected_task_ids=[conflict.task_id],
                        expected_improvement="Reduces blocking time and enables more parallel work",
                    )
                )

                # Suggest prioritization
                suggestions.append(
                    ResolutionSuggestion(
                        suggestion_type="prioritize",
                        description=f"Prioritize task {conflict.task_id} to unblock dependent tasks sooner",
                        affected_task_ids=[conflict.task_id],
                        expected_improvement="Earlier completion of blocking task reduces overall delay",
                    )
                )

            elif conflict.conflict_type == "long_chain":
                # Suggest dependency reordering
                suggestions.append(
                    ResolutionSuggestion(
                        suggestion_type="reorder",
                        description=f"Review dependencies leading to task {conflict.task_id} "
                        f"- some may be removable or parallelizable",
                        affected_task_ids=[conflict.task_id],
                        expected_improvement="Shorter critical path reduces project duration",
                    )
                )

        return suggestions
