# CodeFRAME API Reference

Welcome to the CodeFRAME API documentation. This directory contains comprehensive API references for all multi-agent coordination components.

## Quick Links

### Core Modules

- **[DependencyResolver](./dependency_resolver.md)**: DAG-based task dependency management and cycle detection
- **[AgentPoolManager](./agent_pool_manager.md)**: Worker agent pool management and parallel execution
- **[Worker Agents](./worker_agents.md)**: Specialized agents for backend, frontend, and test tasks
- **[LeadAgent](./lead_agent.md)**: Multi-agent coordination and task orchestration

### Getting Started

1. Start with [Multi-Agent Execution Guide](../user/multi-agent-guide.md) for conceptual overview
2. Review [DependencyResolver API](./dependency_resolver.md) to understand task dependencies
3. Study [AgentPoolManager API](./agent_pool_manager.md) for parallel execution patterns
4. Explore [Worker Agents API](./worker_agents.md) for task-specific agents

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                      LeadAgent                          │
│           (Coordination & Orchestration)                │
└───────────────┬─────────────────────┬──────────────────┘
                │                     │
    ┌───────────▼───────────┐  ┌─────▼────────────────┐
    │  DependencyResolver   │  │  AgentPoolManager    │
    │  (Task Dependencies)  │  │  (Agent Lifecycle)   │
    └───────────────────────┘  └─────┬────────────────┘
                                     │
              ┌──────────────────────┼─────────────────┐
              │                      │                 │
    ┌─────────▼─────────┐  ┌────────▼────────┐ ┌─────▼────────┐
    │ BackendWorker     │  │ FrontendWorker  │ │ TestWorker   │
    │ Agent             │  │ Agent           │ │ Agent        │
    └───────────────────┘  └─────────────────┘ └──────────────┘
```

## Module Index

### Dependency Management

**[DependencyResolver](./dependency_resolver.md)**
- Build dependency graphs from task lists
- Detect circular dependencies
- Identify ready tasks (all dependencies satisfied)
- Track task completion and unblock dependent tasks

**Key Methods**:
```python
resolver = DependencyResolver(tasks)
resolver.build_dependency_graph()
ready_tasks = resolver.get_ready_tasks()
resolver.mark_completed(task_id)
unblocked = resolver.unblock_dependent_tasks(task_id)
```

### Agent Pool Management

**[AgentPoolManager](./agent_pool_manager.md)**
- Create and manage pool of worker agents
- Reuse idle agents for efficiency
- Track agent status (idle, busy, blocked)
- Enforce maximum agent limits
- Broadcast agent lifecycle events

**Key Methods**:
```python
pool = AgentPoolManager(project_id, db, max_agents=10)
agent_id = pool.get_or_create_agent("backend")
pool.mark_agent_busy(agent_id, task_id)
agent = pool.get_agent_instance(agent_id)
pool.mark_agent_idle(agent_id)
```

### Worker Agents

**[FrontendWorkerAgent](./worker_agents.md#frontendworkeragent)**
- React component generation
- TypeScript type definitions
- Tailwind CSS styling
- File creation and import management

**[TestWorkerAgent](./worker_agents.md#testworkeragent)**
- Pytest test generation
- Test execution and validation
- Self-correction loop (3 attempts)
- Test result reporting

**[BackendWorkerAgent](./worker_agents.md#backendworkeragent)**
- FastAPI endpoint creation
- Database model generation
- Business logic implementation
- Data validation schemas

**Key Methods** (all agents):
```python
agent = FrontendWorkerAgent(agent_id="frontend-001")
result = agent.execute_task(task)

if result['status'] == 'completed':
    print(f"Files: {result['files_modified']}")
else:
    print(f"Error: {result['error']}")
```

## Common Patterns

### Parallel Task Execution

```python
from codeframe.agents.agent_pool_manager import AgentPoolManager
from codeframe.agents.dependency_resolver import DependencyResolver
import asyncio

# Initialize components
pool = AgentPoolManager(project_id=1, db=db, max_agents=5)
resolver = DependencyResolver(tasks)
resolver.build_dependency_graph()

# Execute tasks in parallel
async def execute_tasks():
    while not all_tasks_complete():
        ready = resolver.get_ready_tasks()

        # Assign tasks to agents
        for task_id in ready[:5]:  # Max 5 concurrent
            task = get_task(task_id)
            agent_id = pool.get_or_create_agent(task.agent_type)
            pool.mark_agent_busy(agent_id, task_id)

            # Execute asynchronously
            agent = pool.get_agent_instance(agent_id)
            result = await loop.run_in_executor(None, agent.execute_task, task)

            # Update state
            resolver.mark_completed(task_id)
            pool.mark_agent_idle(agent_id)

await execute_tasks()
```

### Dependency Resolution

```python
from codeframe.agents.dependency_resolver import DependencyResolver

# Create tasks with dependencies
tasks = [
    Task(id=1, title="Setup DB", depends_on=""),
    Task(id=2, title="Create API", depends_on="1"),
    Task(id=3, title="Build UI", depends_on="1"),
    Task(id=4, title="Integration Test", depends_on="2,3")
]

# Build dependency graph
resolver = DependencyResolver(tasks)
resolver.build_dependency_graph()

# Execute in dependency order
while not all_complete():
    ready = resolver.get_ready_tasks()

    for task_id in ready:
        execute_task(task_id)
        resolver.mark_completed(task_id)

        # Find newly unblocked tasks
        unblocked = resolver.unblock_dependent_tasks(task_id)
        print(f"Unblocked: {unblocked}")
```

### Agent Reuse

```python
from codeframe.agents.agent_pool_manager import AgentPoolManager

pool = AgentPoolManager(project_id=1, db=db, max_agents=3)

# Execute multiple backend tasks with same agent
for task in backend_tasks:
    # Reuses idle agent if available
    agent_id = pool.get_or_create_agent("backend")

    pool.mark_agent_busy(agent_id, task.id)
    agent = pool.get_agent_instance(agent_id)
    result = agent.execute_task(task)
    pool.mark_agent_idle(agent_id)

# Agent reused 5 times instead of creating 5 agents
status = pool.get_agent_status()
print(f"Agents created: {len(status)}")  # Output: 1
```

## Error Handling

### Circular Dependency Detection

```python
try:
    resolver.build_dependency_graph()
except ValueError as e:
    print(f"Circular dependency detected: {e}")
    # Fix dependencies and retry
```

### Pool Capacity Exceeded

```python
try:
    agent_id = pool.create_agent("backend")
except RuntimeError as e:
    print(f"Pool at capacity: {e}")
    # Use get_or_create_agent() instead to reuse idle agents
    agent_id = pool.get_or_create_agent("backend")
```

### Task Execution Failure

```python
result = agent.execute_task(task)
if result['status'] == 'failed':
    print(f"Task failed: {result['error']}")
    # Retry with different agent or adjust task specification
```

## Performance Guidelines

### Dependency Resolution
- Graph building: O(V + E) - fast even for large graphs
- Cycle detection: O(V + E) - runs once during graph construction
- Ready task lookup: O(V) - optimized with tracking

### Agent Pool Management
- Agent creation: ~100ms (instantiates worker class)
- Agent reuse: ~1ms (retrieves from pool)
- Recommended max_agents: 5-10 based on CPU cores

### Task Execution
- Backend tasks: 2-10 seconds (depends on complexity)
- Frontend tasks: 3-15 seconds (component generation + file writes)
- Test tasks: 5-30 seconds (includes test execution and self-correction)

## Best Practices

1. **Use get_or_create_agent()**: Always prefer over create_agent() for efficiency
2. **Validate dependencies early**: Call build_dependency_graph() before execution
3. **Monitor pool utilization**: Use get_agent_status() to track agent reuse
4. **Handle errors gracefully**: Wrap all agent operations in try-except blocks
5. **Set appropriate limits**: Tune max_agents based on system resources
6. **Parallel execution**: Use asyncio.gather() for concurrent task execution
7. **Clean up resources**: Retire unused agents with retire_agent()

## Testing

### Unit Testing

```python
from unittest.mock import Mock, patch

def test_dependency_resolver():
    tasks = [
        Task(id=1, depends_on=""),
        Task(id=2, depends_on="1")
    ]

    resolver = DependencyResolver(tasks)
    resolver.build_dependency_graph()

    assert resolver.get_ready_tasks() == [1]

    resolver.mark_completed(1)
    assert resolver.get_ready_tasks() == [2]
```

### Integration Testing

```python
import pytest

@pytest.mark.asyncio
async def test_multi_agent_execution():
    pool = AgentPoolManager(project_id=1, db=db, max_agents=3)
    resolver = DependencyResolver(tasks)

    # Execute tasks
    # ... (see integration test examples in respective API docs)

    # Verify
    assert all(task.status == 'completed' for task in tasks)
    assert len(pool.get_agent_status()) <= 3  # Max agents respected
```

## Migration Guide

### From Single-Agent to Multi-Agent

**Before (Sprint 3)**:
```python
lead_agent = LeadAgent(project_id=1, db=db)
result = lead_agent.execute_task(task)
```

**After (Sprint 4)**:
```python
lead_agent = LeadAgent(project_id=1, db=db)
summary = await lead_agent.start_multi_agent_execution(max_concurrent=5)
print(f"Completed: {summary['completed']}/{summary['total_tasks']}")
```

### Backward Compatibility

All Sprint 3 functionality remains available. Single-agent execution still works:

```python
# Sprint 3 style - still supported
lead_agent = LeadAgent(project_id=1, db=db)
result = lead_agent.execute_task(task)  # Uses BackendWorkerAgent internally
```

## Troubleshooting

See individual API documentation for detailed troubleshooting:
- [DependencyResolver Troubleshooting](./dependency_resolver.md#error-handling)
- [AgentPoolManager Troubleshooting](./agent_pool_manager.md#error-handling)
- [Worker Agents Troubleshooting](./worker_agents.md#troubleshooting)

## Contributing

When adding new agents or modifying APIs:
1. Update relevant API documentation
2. Add usage examples
3. Document error conditions
4. Include performance considerations
5. Update this README with new features

## Support

- **Documentation**: [docs/](../)
- **Issues**: [GitHub Issues](https://github.com/frankbria/codeframe/issues)
- **Examples**: [examples/](../../examples/)
- **Tests**: [tests/](../../tests/)

---

**Last Updated**: 2025-10-26
**Version**: Sprint 4 (Multi-Agent Coordination)
