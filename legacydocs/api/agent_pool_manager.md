# AgentPoolManager API Reference

## Overview

The `AgentPoolManager` class manages a pool of worker agents for parallel task execution. It handles agent creation, reuse, status tracking, and lifecycle management.

## Class: AgentPoolManager

**Module**: `codeframe.agents.agent_pool_manager`

**Purpose**: Manage pool of worker agents to enable parallel task execution and efficient resource utilization.

### Constructor

```python
def __init__(
    self,
    project_id: int,
    db: Database,
    ws_manager=None,
    max_agents: int = 10,
    api_key: Optional[str] = None
)
```

**Parameters**:
- `project_id` (int): Project ID for this pool
- `db` (Database): Database instance for persistence
- `ws_manager` (WebSocketManager, optional): WebSocket manager for broadcasts
- `max_agents` (int, optional): Maximum concurrent agents (default: 10)
- `api_key` (str, optional): Anthropic API key (uses env var if not provided)

**Example**:
```python
from codeframe.agents.agent_pool_manager import AgentPoolManager
from codeframe.persistence.database import Database

db = Database("codeframe.db")
db.initialize()

pool = AgentPoolManager(
    project_id=1,
    db=db,
    max_agents=5
)
```

### Methods

#### create_agent(agent_type: str)

Create new worker agent of specified type.

```python
def create_agent(self, agent_type: str) -> str
```

**Parameters**:
- `agent_type` (str): Type of agent ("backend", "frontend", "test", "backend-worker", "frontend-specialist", "test-engineer")

**Returns**:
- `str`: Agent ID of created agent

**Raises**:
- `ValueError`: If unknown agent type
- `RuntimeError`: If pool at maximum capacity

**Example**:
```python
agent_id = pool.create_agent("backend")
print(f"Created agent: {agent_id}")  # "backend-worker-001"
```

#### get_or_create_agent(agent_type: str)

Get idle agent of specified type or create new one.

```python
def get_or_create_agent(self, agent_type: str) -> str
```

**Parameters**:
- `agent_type` (str): Type of agent needed

**Returns**:
- `str`: Agent ID of available agent (reused or newly created)

**Description**: Reuses idle agents before creating new ones to minimize overhead.

**Example**:
```python
# First call - creates new agent
agent_id = pool.get_or_create_agent("frontend")

# Later, after agent marked idle
# Second call - reuses existing idle agent
agent_id2 = pool.get_or_create_agent("frontend")
# Returns same agent_id if agent is idle
```

#### mark_agent_busy(agent_id: str, task_id: int)

Mark agent as busy with a task.

```python
def mark_agent_busy(self, agent_id: str, task_id: int) -> None
```

**Parameters**:
- `agent_id` (str): ID of agent to mark busy
- `task_id` (int): ID of task being executed

**Raises**:
- `KeyError`: If agent not in pool

**Example**:
```python
pool.mark_agent_busy("backend-worker-001", task_id=42)
```

#### mark_agent_idle(agent_id: str)

Mark agent as idle and ready for new task.

```python
def mark_agent_idle(self, agent_id: str) -> None
```

**Parameters**:
- `agent_id` (str): ID of agent to mark idle

**Raises**:
- `KeyError`: If agent not in pool

**Example**:
```python
# After task completes
pool.mark_agent_idle("backend-worker-001")
```

#### mark_agent_blocked(agent_id: str, blocked_by: list)

Mark agent as blocked by dependencies.

```python
def mark_agent_blocked(self, agent_id: str, blocked_by: list) -> None
```

**Parameters**:
- `agent_id` (str): ID of agent to mark blocked
- `blocked_by` (list): List of task IDs blocking this agent

**Raises**:
- `KeyError`: If agent not in pool

**Example**:
```python
pool.mark_agent_blocked("frontend-specialist-001", blocked_by=[1, 2])
```

#### retire_agent(agent_id: str)

Retire agent and remove from pool.

```python
def retire_agent(self, agent_id: str) -> None
```

**Parameters**:
- `agent_id` (str): ID of agent to retire

**Raises**:
- `KeyError`: If agent not in pool

**Example**:
```python
# Clean up agent after all tasks complete
pool.retire_agent("backend-worker-001")
```

#### get_agent_status()

Get status of all agents in pool.

```python
def get_agent_status(self) -> Dict[str, Dict[str, Any]]
```

**Returns**:
- `Dict[str, Dict[str, Any]]`: Mapping of agent_id → status info

**Status Info Structure**:
```python
{
    "agent_id": {
        "agent_type": "backend",
        "status": "busy",  # idle | busy | blocked
        "current_task": 42,
        "tasks_completed": 5,
        "blocked_by": None  # or list of task IDs
    }
}
```

**Example**:
```python
status = pool.get_agent_status()
for agent_id, info in status.items():
    print(f"{agent_id}: {info['status']} (completed: {info['tasks_completed']})")
```

#### get_agent_instance(agent_id: str)

Get agent instance for task execution.

```python
def get_agent_instance(self, agent_id: str) -> Any
```

**Parameters**:
- `agent_id` (str): ID of agent to retrieve

**Returns**:
- Agent instance (BackendWorkerAgent | FrontendWorkerAgent | TestWorkerAgent)

**Raises**:
- `KeyError`: If agent not in pool

**Example**:
```python
agent = pool.get_agent_instance("backend-worker-001")
result = agent.execute_task(task)
```

#### clear()

Clear all agents from pool (for testing/reset).

```python
def clear(self) -> None
```

**Example**:
```python
# Reset pool state
pool.clear()
```

## Properties

### agent_pool

```python
@property
def agent_pool(self) -> Dict[str, Dict[str, Any]]
```

Get the internal agent pool state.

**Returns**:
- `Dict[str, Dict[str, Any]]`: Agent pool mapping

## Usage Examples

### Basic Agent Pool Management

```python
from codeframe.agents.agent_pool_manager import AgentPoolManager
from codeframe.persistence.database import Database

# Initialize
db = Database("codeframe.db")
db.initialize()

pool = AgentPoolManager(project_id=1, db=db, max_agents=3)

# Create agents
backend_id = pool.create_agent("backend")
frontend_id = pool.create_agent("frontend")

# Assign task
pool.mark_agent_busy(backend_id, task_id=1)

# Execute task
agent = pool.get_agent_instance(backend_id)
result = agent.execute_task(task)

# Mark complete
pool.mark_agent_idle(backend_id)

# Get status
status = pool.get_agent_status()
print(status)
```

### Agent Reuse Pattern

```python
# Execute multiple tasks with same agent type
for task in backend_tasks:
    # Reuses idle agent or creates new one
    agent_id = pool.get_or_create_agent("backend")
    pool.mark_agent_busy(agent_id, task.id)

    agent = pool.get_agent_instance(agent_id)
    result = agent.execute_task(task)

    pool.mark_agent_idle(agent_id)
```

### Parallel Execution

```python
import asyncio

async def execute_task_parallel(task, pool):
    agent_id = pool.get_or_create_agent(task.agent_type)
    pool.mark_agent_busy(agent_id, task.id)

    agent = pool.get_agent_instance(agent_id)

    # Execute in thread pool
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, agent.execute_task, task)

    pool.mark_agent_idle(agent_id)
    return result

# Execute 3 tasks in parallel
tasks = [task1, task2, task3]
results = await asyncio.gather(*[
    execute_task_parallel(t, pool) for t in tasks
])
```

### Agent Pool Monitoring

```python
def print_pool_stats(pool):
    """Print current pool statistics."""
    status = pool.get_agent_status()

    total = len(status)
    idle = sum(1 for s in status.values() if s['status'] == 'idle')
    busy = sum(1 for s in status.values() if s['status'] == 'busy')
    blocked = sum(1 for s in status.values() if s['status'] == 'blocked')

    print(f"Pool Stats: {total} total, {idle} idle, {busy} busy, {blocked} blocked")

    for agent_id, info in status.items():
        print(f"  {agent_id}: {info['status']} - {info['tasks_completed']} completed")

# Monitor pool
print_pool_stats(pool)
```

## Error Handling

### RuntimeError: Pool at maximum capacity

**Cause**: Attempting to create agent when pool has reached `max_agents` limit

**Solution**: Wait for agents to become idle or increase `max_agents`

```python
try:
    agent_id = pool.create_agent("backend")
except RuntimeError as e:
    print(f"Pool full: {e}")
    # Wait for idle agent instead
    agent_id = pool.get_or_create_agent("backend")
```

### KeyError: Agent not in pool

**Cause**: Attempting to access agent that doesn't exist or was retired

**Solution**: Check agent exists before accessing

```python
status = pool.get_agent_status()
if agent_id in status:
    pool.mark_agent_idle(agent_id)
else:
    print(f"Agent {agent_id} not found in pool")
```

## Thread Safety

The `AgentPoolManager` uses `RLock` (reentrant lock) for thread safety. All public methods are thread-safe and can be called from multiple threads concurrently.

**Note**: `RLock` is used instead of `Lock` to allow methods to call each other while holding the lock (e.g., `get_or_create_agent` calls `create_agent`).

## WebSocket Events

When `ws_manager` is provided, the pool broadcasts lifecycle events:

- **agent_created**: New agent created
- **agent_retired**: Agent removed from pool

**Event Payload**:
```json
{
    "type": "agent_created",
    "project_id": 1,
    "agent_id": "backend-worker-001",
    "agent_type": "backend",
    "tasks_completed": 0,
    "timestamp": "2025-10-25T23:55:00Z"
}
```

## Performance Considerations

- **Agent Creation**: ~100ms per agent (instantiates worker class)
- **Agent Reuse**: ~1ms (retrieves from pool)
- **Max Agents**: Default 10, adjust based on system resources
- **Memory**: Each agent ~10MB RAM

## Best Practices

1. **Reuse agents**: Always use `get_or_create_agent()` instead of `create_agent()` directly
2. **Retire unused agents**: Call `retire_agent()` for long-idle agents to free memory
3. **Monitor pool**: Use `get_agent_status()` to track utilization
4. **Set appropriate limits**: Tune `max_agents` based on CPU cores and memory
5. **Handle errors**: Wrap pool operations in try-except for robustness

## See Also

- [DependencyResolver API](./dependency_resolver.md)
- [LeadAgent API](./lead_agent.md)
- [Worker Agent APIs](./worker_agents.md)
- [Multi-Agent Execution Guide](../user/multi-agent-guide.md)
