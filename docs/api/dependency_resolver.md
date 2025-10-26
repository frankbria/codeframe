# DependencyResolver API Reference

## Overview

The `DependencyResolver` class provides DAG-based task dependency resolution for the multi-agent coordination system. It manages task dependencies, detects cycles, and determines which tasks are ready for execution.

## Class: DependencyResolver

**Module**: `codeframe.agents.dependency_resolver`

**Purpose**: Manage task dependencies and determine execution order based on a directed acyclic graph (DAG).

### Constructor

```python
def __init__(self, tasks: List[Task])
```

**Parameters**:
- `tasks` (List[Task]): List of Task objects to build dependency graph from

**Example**:
```python
from codeframe.agents.dependency_resolver import DependencyResolver
from codeframe.core.models import Task

tasks = [
    Task(id=1, title="Backend API", depends_on=""),
    Task(id=2, title="Frontend UI", depends_on="1"),
    Task(id=3, title="Tests", depends_on="1,2")
]

resolver = DependencyResolver(tasks)
```

### Methods

#### build_dependency_graph()

Build directed acyclic graph (DAG) from task list.

```python
def build_dependency_graph(self) -> None
```

**Raises**:
- `ValueError`: If circular dependencies detected

**Example**:
```python
resolver.build_dependency_graph()
```

#### get_ready_tasks()

Get list of tasks with all dependencies satisfied.

```python
def get_ready_tasks(self) -> List[int]
```

**Returns**:
- `List[int]`: Task IDs that are ready for execution (all dependencies completed)

**Example**:
```python
ready_task_ids = resolver.get_ready_tasks()
# Returns: [1] (task with no dependencies)

# After completing task 1:
resolver.mark_completed(1)
ready_task_ids = resolver.get_ready_tasks()
# Returns: [2] (task 2's dependency is now satisfied)
```

#### mark_completed(task_id: int)

Mark a task as completed and update dependency tracking.

```python
def mark_completed(self, task_id: int) -> None
```

**Parameters**:
- `task_id` (int): ID of completed task

**Example**:
```python
resolver.mark_completed(1)
```

#### unblock_dependent_tasks(task_id: int)

Find tasks that are newly unblocked after completing specified task.

```python
def unblock_dependent_tasks(self, task_id: int) -> List[int]
```

**Parameters**:
- `task_id` (int): ID of recently completed task

**Returns**:
- `List[int]`: Task IDs that are now ready (were blocked by this task)

**Example**:
```python
# Complete task 1
resolver.mark_completed(1)

# Find newly unblocked tasks
unblocked = resolver.unblock_dependent_tasks(1)
# Returns: [2] (task 2 was waiting for task 1)
```

#### detect_cycles()

Detect circular dependencies in the graph using depth-first search.

```python
def detect_cycles(self) -> bool
```

**Returns**:
- `bool`: True if cycles detected, False otherwise

**Example**:
```python
if resolver.detect_cycles():
    print("Warning: Circular dependencies found!")
```

#### validate_dependencies()

Validate that adding a dependency won't create a cycle.

```python
def validate_dependencies(self, task_id: int, depends_on: List[int]) -> bool
```

**Parameters**:
- `task_id` (int): Task ID to add dependency to
- `depends_on` (List[int]): List of dependency task IDs

**Returns**:
- `bool`: True if dependencies are valid (no cycles), False otherwise

**Example**:
```python
# Check if adding dependency is safe
is_valid = resolver.validate_dependencies(task_id=3, depends_on=[1, 2])
if is_valid:
    # Safe to add dependency
    task.depends_on = "1,2"
```

## Properties

### graph

```python
@property
def graph(self) -> Dict[int, List[int]]
```

Get the dependency graph.

**Returns**:
- `Dict[int, List[int]]`: Mapping of task_id → list of dependency task_ids

### completed_tasks

```python
@property
def completed_tasks(self) -> Set[int]
```

Get set of completed task IDs.

**Returns**:
- `Set[int]`: Task IDs that have been marked completed

## Usage Examples

### Basic Usage

```python
from codeframe.agents.dependency_resolver import DependencyResolver
from codeframe.core.models import Task

# Create tasks with dependencies
tasks = [
    Task(id=1, title="Setup DB", depends_on=""),
    Task(id=2, title="Create API", depends_on="1"),
    Task(id=3, title="Build UI", depends_on="1"),
    Task(id=4, title="Integration Test", depends_on="2,3")
]

# Initialize resolver
resolver = DependencyResolver(tasks)
resolver.build_dependency_graph()

# Get initial ready tasks
ready = resolver.get_ready_tasks()
print(f"Ready tasks: {ready}")  # [1]

# Complete task 1
resolver.mark_completed(1)

# Get newly ready tasks
ready = resolver.get_ready_tasks()
print(f"Ready tasks: {ready}")  # [2, 3]
```

### Cycle Detection

```python
# Tasks with circular dependency
tasks = [
    Task(id=1, title="Task 1", depends_on="2"),  # depends on 2
    Task(id=2, title="Task 2", depends_on="1")   # depends on 1 → cycle!
]

resolver = DependencyResolver(tasks)

try:
    resolver.build_dependency_graph()
except ValueError as e:
    print(f"Error: {e}")  # "Circular dependency detected"
```

### Validation Before Adding Dependency

```python
resolver = DependencyResolver(tasks)
resolver.build_dependency_graph()

# Check if adding dependency would create cycle
task_id = 2
new_dependency = [3]

if resolver.validate_dependencies(task_id, new_dependency):
    # Safe to add
    task.depends_on = "3"
else:
    print("Cannot add dependency - would create cycle")
```

## Error Handling

### ValueError: Circular dependency detected

**Cause**: Task dependencies form a cycle (A → B → A)

**Solution**: Review dependency chain and remove circular references

**Example**:
```python
try:
    resolver.build_dependency_graph()
except ValueError as e:
    print(f"Dependency error: {e}")
    # Fix circular dependencies in task list
```

## Performance Considerations

- **Graph Building**: O(V + E) where V = tasks, E = dependencies
- **Cycle Detection**: O(V + E) using depth-first search
- **Ready Tasks**: O(V) to check all tasks
- **Memory**: O(V + E) for graph storage

## Thread Safety

The `DependencyResolver` is **not thread-safe**. For concurrent access:

1. Use separate resolver instances per thread
2. Or wrap calls in a lock:

```python
from threading import Lock

lock = Lock()

with lock:
    ready = resolver.get_ready_tasks()
```

## See Also

- [AgentPoolManager API](./agent_pool_manager.md)
- [LeadAgent API](./lead_agent.md)
- [Multi-Agent Execution Guide](../user/multi-agent-guide.md)
