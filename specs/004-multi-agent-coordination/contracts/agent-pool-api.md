# Agent Pool Manager API Contract

## Overview

The `AgentPoolManager` manages a pool of worker agents for parallel task execution. It handles agent lifecycle (creation, retirement), status tracking (idle, busy, blocked), and resource limits.

**File Location:** `/home/frankbria/projects/codeframe/codeframe/agents/agent_pool_manager.py`

---

## Class: AgentPoolManager

### Constructor

```python
__init__(
    project_id: int,
    db: Database,
    ws_manager=None,
    max_agents: int = 10,
    api_key: Optional[str] = None
)
```

**Purpose:** Initialize the Agent Pool Manager for a specific project.

**Parameters:**
- `project_id` (int): Project ID for this agent pool
- `db` (Database): Database instance for task/status management
- `ws_manager` (optional): WebSocket ConnectionManager for real-time broadcasts
- `max_agents` (int, default=10): Maximum number of concurrent agents allowed
- `api_key` (Optional[str]): Anthropic API key (falls back to `ANTHROPIC_API_KEY` env var)

**State:**
- `agent_pool: Dict[str, Dict[str, Any]]`: Maps agent_id → agent_info
- `next_agent_number: int`: Counter for generating unique agent IDs
- `lock: RLock`: Thread-safe reentrant lock for pool operations

---

## Public Methods

### create_agent

```python
def create_agent(agent_type: str) -> str
```

**Purpose:** Create a new worker agent of the specified type and add it to the pool.

**Parameters:**
- `agent_type` (str): Type of agent to create. Valid values:
  - `"backend"` or `"backend-worker"`: Backend Python developer
  - `"frontend"` or `"frontend-specialist"`: Frontend React/TypeScript developer
  - `"test"` or `"test-engineer"`: Test/pytest specialist

**Returns:**
- `agent_id` (str): Unique identifier for created agent (format: `{type}-worker-{number:03d}`)

**Raises:**
- `ValueError`: Unknown agent type
- `RuntimeError`: Agent pool at maximum capacity (`max_agents` reached)

**Side Effects:**
- Creates agent instance (BackendWorkerAgent, FrontendWorkerAgent, or TestWorkerAgent)
- Adds agent to `agent_pool` with status="idle"
- Increments `next_agent_number`
- Broadcasts `agent_created` event via WebSocket (if `ws_manager` available)

**Thread Safety:** Uses internal lock for atomic pool modifications

**Example:**
```python
agent_id = pool.create_agent("backend")
# Returns: "backend-worker-001"
```

---

### get_or_create_agent

```python
def get_or_create_agent(agent_type: str) -> str
```

**Purpose:** Get an idle agent of the specified type, or create a new one if none available. Implements agent reuse to minimize overhead.

**Parameters:**
- `agent_type` (str): Type of agent needed (same values as `create_agent`)

**Returns:**
- `agent_id` (str): ID of available agent (existing or newly created)

**Behavior:**
1. Searches pool for idle agent of matching type
2. If found, returns existing agent_id
3. If not found, calls `create_agent(agent_type)` and returns new agent_id

**Thread Safety:** Uses internal lock

**Example:**
```python
# First call creates new agent
agent1 = pool.get_or_create_agent("backend")  # Creates backend-worker-001

# Mark it idle
pool.mark_agent_idle(agent1)

# Second call reuses the idle agent
agent2 = pool.get_or_create_agent("backend")  # Returns backend-worker-001 (same agent)
```

---

### mark_agent_busy

```python
def mark_agent_busy(agent_id: str, task_id: int) -> None
```

**Purpose:** Mark an agent as busy with a specific task.

**Parameters:**
- `agent_id` (str): ID of agent to mark busy
- `task_id` (int): ID of task being executed

**Side Effects:**
- Sets agent status to "busy"
- Sets agent's `current_task` to `task_id`

**Raises:**
- `KeyError`: Agent not found in pool

**Thread Safety:** Uses internal lock

---

### mark_agent_idle

```python
def mark_agent_idle(agent_id: str) -> None
```

**Purpose:** Mark agent as idle and ready for new task. Called after task completion.

**Parameters:**
- `agent_id` (str): ID of agent to mark idle

**Side Effects:**
- Sets agent status to "idle"
- Clears agent's `current_task` (sets to None)
- Increments agent's `tasks_completed` counter

**Raises:**
- `KeyError`: Agent not found in pool

**Thread Safety:** Uses internal lock

---

### mark_agent_blocked

```python
def mark_agent_blocked(agent_id: str, blocked_by: list) -> None
```

**Purpose:** Mark agent as blocked by task dependencies.

**Parameters:**
- `agent_id` (str): ID of agent to mark blocked
- `blocked_by` (list): List of task IDs blocking this agent

**Side Effects:**
- Sets agent status to "blocked"
- Sets agent's `blocked_by` to the dependency list

**Raises:**
- `KeyError`: Agent not found in pool

**Thread Safety:** Uses internal lock

---

### retire_agent

```python
def retire_agent(agent_id: str) -> None
```

**Purpose:** Retire agent and remove from pool. Used for cleanup or capacity management.

**Parameters:**
- `agent_id` (str): ID of agent to retire

**Side Effects:**
- Removes agent from `agent_pool`
- Broadcasts `agent_retired` event via WebSocket (if `ws_manager` available)

**Raises:**
- `KeyError`: Agent not found in pool

**Thread Safety:** Uses internal lock

**Example:**
```python
pool.retire_agent("backend-worker-001")
# Agent removed from pool, capacity freed
```

---

### get_agent_status

```python
def get_agent_status() -> Dict[str, Dict[str, Any]]
```

**Purpose:** Get status snapshot of all agents in pool.

**Returns:**
Dictionary mapping agent_id → status info:
```python
{
    "backend-worker-001": {
        "agent_type": "backend",
        "status": "busy",  # idle | busy | blocked
        "current_task": 42,  # task ID or None
        "tasks_completed": 5,
        "blocked_by": None  # list of task IDs or None
    },
    "frontend-worker-001": {
        "agent_type": "frontend",
        "status": "idle",
        "current_task": None,
        "tasks_completed": 3,
        "blocked_by": None
    }
}
```

**Thread Safety:** Uses internal lock

---

### get_agent_instance

```python
def get_agent_instance(agent_id: str) -> WorkerAgent
```

**Purpose:** Get the actual agent instance for direct task execution.

**Parameters:**
- `agent_id` (str): ID of agent to retrieve

**Returns:**
- Agent instance (BackendWorkerAgent, FrontendWorkerAgent, or TestWorkerAgent)

**Raises:**
- `KeyError`: Agent not found in pool

**Thread Safety:** Uses internal lock

**Example:**
```python
agent = pool.get_agent_instance("backend-worker-001")
result = await agent.execute_task(task)
```

---

### clear

```python
def clear() -> None
```

**Purpose:** Clear all agents from pool. Used for testing/reset scenarios.

**Side Effects:**
- Removes all agents from `agent_pool`
- Resets `next_agent_number` to 1

**Thread Safety:** Uses internal lock

---

## Agent Info Schema

Each agent in `agent_pool` is stored as:

```python
{
    "instance": WorkerAgent,        # Actual agent instance
    "status": str,                  # "idle" | "busy" | "blocked"
    "current_task": Optional[int],  # Task ID or None
    "agent_type": str,              # "backend" | "frontend" | "test"
    "tasks_completed": int,         # Counter
    "blocked_by": Optional[list]    # List of task IDs or None
}
```

---

## Integration Points

### WebSocket Broadcasts (cf-45)

When `ws_manager` is provided, the following events are broadcast:

1. **Agent Creation** (`create_agent`):
   - Event: `agent_created`
   - Fields: `agent_id`, `agent_type`, `tasks_completed`, `timestamp`

2. **Agent Retirement** (`retire_agent`):
   - Event: `agent_retired`
   - Fields: `agent_id`, `tasks_completed`, `timestamp`

### Worker Agent Types

- **BackendWorkerAgent** (cf-41): Python/FastAPI development
- **FrontendWorkerAgent** (cf-48): React/TypeScript components
- **TestWorkerAgent** (cf-49): pytest test generation

---

## Thread Safety

All public methods use a **reentrant lock (RLock)** to ensure thread-safe pool operations. Multiple threads can safely call pool methods concurrently.

---

## Error Handling

| Error | Condition | Recovery |
|-------|-----------|----------|
| `ValueError` | Unknown agent type | Validate type before calling `create_agent` |
| `RuntimeError` | Pool at max capacity | Retire idle agents or increase `max_agents` |
| `KeyError` | Agent not in pool | Check `get_agent_status()` before accessing |

---

## Usage Example

```python
from codeframe.agents.agent_pool_manager import AgentPoolManager
from codeframe.persistence.database import Database

# Initialize
db = Database("project.db")
pool = AgentPoolManager(project_id=1, db=db, max_agents=10)

# Create agents
backend_id = pool.create_agent("backend")   # "backend-worker-001"
frontend_id = pool.create_agent("frontend") # "frontend-worker-001"

# Assign tasks
pool.mark_agent_busy(backend_id, task_id=42)

# Get status
status = pool.get_agent_status()
print(status[backend_id]["status"])  # "busy"

# Complete task
pool.mark_agent_idle(backend_id)

# Reuse agent
agent_id = pool.get_or_create_agent("backend")  # Returns backend-worker-001

# Cleanup
pool.retire_agent(backend_id)
```

---

## Sprint Context

**Sprint 4 (cf-24):** Multi-Agent Coordination
**Dependencies:**
- Database (cf-8)
- BackendWorkerAgent (cf-41)
- FrontendWorkerAgent (cf-48)
- TestWorkerAgent (cf-49)
- WebSocket Broadcasts (cf-45)

**Related Specs:**
- [Worker Agent Interface](./worker-agent-interface.md)
- [WebSocket Events](./websocket-events.md)
