# Data Model: Multi-Agent Coordination

**Feature**: 004-multi-agent-coordination
**Sprint**: 4
**Status**: Implemented
**Last Updated**: 2025-11-08

## Overview

This document describes the data model for multi-agent coordination in CodeFRAME, including database schema, in-memory structures, TypeScript types, and WebSocket message formats.

---

## Database Schema

### tasks table (Enhanced)

The existing `tasks` table was enhanced with dependency tracking:

```sql
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    issue_id INTEGER REFERENCES issues(id),
    task_number TEXT,
    parent_issue_number TEXT,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT CHECK(status IN ('pending', 'assigned', 'in_progress', 'blocked', 'completed', 'failed')),
    assigned_to TEXT,
    depends_on TEXT,  -- JSON array of task IDs this task depends on (e.g., "[]", "[1,2]")
    can_parallelize BOOLEAN DEFAULT FALSE,
    priority INTEGER CHECK(priority BETWEEN 0 AND 4),
    workflow_step INTEGER,
    requires_mcp BOOLEAN DEFAULT FALSE,
    estimated_tokens INTEGER,
    actual_tokens INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
)
```

**Key Enhancement**: `depends_on` column stores JSON array for backward compatibility and simple queries.

---

### task_dependencies table (New)

Junction table for efficient dependency graph queries:

```sql
CREATE TABLE IF NOT EXISTS task_dependencies (
    id INTEGER PRIMARY KEY,
    task_id INTEGER NOT NULL,
    depends_on_task_id INTEGER NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id),
    FOREIGN KEY (depends_on_task_id) REFERENCES tasks(id),
    UNIQUE(task_id, depends_on_task_id)
)

-- Indexes for bidirectional queries
CREATE INDEX IF NOT EXISTS idx_task_dependencies_task
    ON task_dependencies(task_id)

CREATE INDEX IF NOT EXISTS idx_task_dependencies_depends_on
    ON task_dependencies(depends_on_task_id)
```

**Purpose**:
- Efficiently find all dependencies for a task (forward lookup)
- Efficiently find all tasks blocked by a given task (reverse lookup)
- Enforce uniqueness to prevent duplicate dependency relationships

---

## In-Memory Structures

### Agent Pool (`AgentPoolManager.agent_pool`)

The agent pool is maintained in memory as a thread-safe dictionary:

```python
agent_pool: Dict[str, Dict[str, Any]] = {
    "agent_id": {
        "instance": WorkerAgent,           # Agent instance (BackendWorkerAgent, etc.)
        "status": str,                     # "idle" | "busy" | "blocked"
        "current_task": Optional[int],     # Task ID currently being executed
        "agent_type": str,                 # "backend" | "frontend" | "test"
        "tasks_completed": int,            # Historical completion count
        "blocked_by": Optional[List[int]]  # Task IDs blocking this agent (if status="blocked")
    }
}
```

**File**: `/home/frankbria/projects/codeframe/codeframe/agents/agent_pool_manager.py`

**Thread Safety**: All operations use `threading.RLock` for reentrancy.

**Status Transitions**:
- `idle` → `busy`: Agent picks up a task
- `busy` → `idle`: Task completes successfully
- `busy` → `blocked`: Task cannot proceed due to dependencies
- `blocked` → `idle`: Dependencies resolved, agent freed

**Lifecycle**:
1. `create_agent(agent_type)`: Instantiate and add to pool
2. `get_or_create_agent(agent_type)`: Reuse idle agents before creating new ones
3. `mark_agent_busy(agent_id, task_id)`: Assign task
4. `mark_agent_idle(agent_id)`: Release agent, increment `tasks_completed`
5. `mark_agent_blocked(agent_id, blocked_by)`: Mark blocked by dependencies
6. `retire_agent(agent_id)`: Remove from pool and cleanup

---

## Python Data Models

### Task (Enhanced)

```python
@dataclass
class Task:
    """Atomic development task within an issue."""
    id: Optional[int] = None
    project_id: Optional[int] = None
    issue_id: Optional[int] = None
    task_number: str = ""              # e.g., "1.5.3"
    parent_issue_number: str = ""      # e.g., "1.5"
    title: str = ""
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    assigned_to: Optional[str] = None
    depends_on: str = ""               # JSON string: previous task number(s)
    can_parallelize: bool = False
    priority: int = 2                  # 0-4, 0 = highest
    workflow_step: int = 1
    requires_mcp: bool = False
    estimated_tokens: int = 0
    actual_tokens: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
```

### TaskStatus (Enhanced)

```python
class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"         # NEW: Task waiting on dependencies
    COMPLETED = "completed"
    FAILED = "failed"
```

**File**: `/home/frankbria/projects/codeframe/codeframe/core/models.py`

---

## TypeScript Types (Frontend)

### Agent Types

```typescript
/**
 * Agent type specializations supported by the system
 */
export type AgentType =
  | 'lead'                  // Orchestrates other agents
  | 'backend-worker'        // Handles backend code
  | 'frontend-specialist'   // Handles frontend code
  | 'test-engineer';        // Writes and runs tests

/**
 * Current activity status of an agent
 */
export type AgentStatus =
  | 'idle'      // Available for work
  | 'working'   // Executing a task
  | 'blocked';  // Waiting on blocker resolution

/**
 * Individual agent entity with conflict resolution timestamp
 */
export interface Agent {
  id: string;                       // e.g., "backend-worker-001"
  type: AgentType;
  status: AgentStatus;
  provider: string;                 // "anthropic"
  maturity: AgentMaturity;
  current_task?: CurrentTask;
  blocker?: string;
  context_tokens: number;
  tasks_completed: number;
  timestamp: number;                // Unix ms for conflict resolution
}

export interface CurrentTask {
  id: number;
  title: string;
}
```

### Task Types

```typescript
/**
 * Task execution status
 */
export type TaskStatus =
  | 'pending'       // Not started, no blockers
  | 'in_progress'   // Agent actively working
  | 'blocked'       // Waiting on dependencies
  | 'completed';    // Finished

/**
 * Work item that can be assigned to agents
 */
export interface Task {
  id: number;
  title: string;
  status: TaskStatus;
  agent_id?: string;               // Assigned agent (if any)
  blocked_by?: number[];           // Task IDs blocking this task
  progress?: number;               // Completion percentage (0-100)
  timestamp: number;               // Unix ms from backend
}
```

### Activity Types

```typescript
/**
 * Activity feed event categories
 */
export type ActivityType =
  | 'task_assigned'
  | 'task_completed'
  | 'task_blocked'
  | 'task_unblocked'
  | 'agent_created'
  | 'agent_retired'
  | 'test_result'
  | 'commit_created'
  | 'correction_attempt'
  | 'activity_update'
  | 'blocker_created'
  | 'blocker_resolved';

export interface ActivityItem {
  timestamp: string;                // ISO 8601 from backend
  type: ActivityType;
  agent: string;                    // Agent ID or "system"
  message: string;
}
```

**File**: `/home/frankbria/projects/codeframe/web-ui/src/types/agentState.ts`

---

## WebSocket Message Types

All WebSocket messages include common fields:
- `type`: Message type identifier
- `project_id`: Project ID
- `timestamp`: ISO 8601 timestamp (UTC with 'Z' suffix)

### 1. agent_created

**Trigger**: New agent added to pool
**Broadcast**: `AgentPoolManager.create_agent()`

```typescript
{
  type: "agent_created",
  project_id: number,
  agent_id: string,           // e.g., "backend-worker-001"
  agent_type: string,         // e.g., "backend-worker"
  status: "idle",
  tasks_completed: number,    // Initial: 0
  timestamp: string           // ISO 8601
}
```

---

### 2. agent_retired

**Trigger**: Agent removed from pool
**Broadcast**: `AgentPoolManager.retire_agent()`

```typescript
{
  type: "agent_retired",
  project_id: number,
  agent_id: string,
  tasks_completed: number,    // Final completion count
  timestamp: string
}
```

---

### 3. task_assigned

**Trigger**: Task assigned to agent
**Broadcast**: Task assignment logic

```typescript
{
  type: "task_assigned",
  project_id: number,
  task_id: number,
  agent_id: string,
  task_title?: string,        // Optional for UI display
  timestamp: string
}
```

---

### 4. task_blocked

**Trigger**: Task cannot proceed due to dependencies
**Broadcast**: Dependency resolver

```typescript
{
  type: "task_blocked",
  project_id: number,
  task_id: number,
  blocked_by: number[],       // Array of blocking task IDs
  blocked_count: number,      // Count of blockers
  task_title?: string,
  timestamp: string
}
```

---

### 5. task_unblocked

**Trigger**: Dependencies resolved, task can proceed
**Broadcast**: Dependency resolver

```typescript
{
  type: "task_unblocked",
  project_id: number,
  task_id: number,
  unblocked_by?: number,      // Optional: task that unblocked this one
  task_title?: string,
  timestamp: string
}
```

**File**: `/home/frankbria/projects/codeframe/codeframe/ui/websocket_broadcasts.py`

---

## Database Operations

### Task Dependency Management

The `Database` class provides methods for managing task dependencies:

#### Add Dependency

```python
def add_task_dependency(task_id: int, depends_on_task_id: int) -> None:
    """
    Add a dependency relationship between tasks.

    Updates both:
    - task_dependencies junction table
    - tasks.depends_on JSON array
    """
```

#### Query Dependencies

```python
def get_task_dependencies(task_id: int) -> list:
    """Get all tasks that the given task depends on (forward lookup)."""

def get_dependent_tasks(task_id: int) -> list:
    """Get all tasks that depend on the given task (reverse lookup)."""
```

#### Remove Dependencies

```python
def remove_task_dependency(task_id: int, depends_on_task_id: int) -> None:
    """Remove a specific dependency relationship."""

def clear_all_task_dependencies(task_id: int) -> None:
    """Remove all dependencies for a task."""
```

**File**: `/home/frankbria/projects/codeframe/codeframe/persistence/database.py` (lines 1606-1730)

---

## State Synchronization

### Conflict Resolution

The frontend uses **last-write-wins** based on backend timestamps:

1. Backend includes Unix millisecond timestamp in all state updates
2. Frontend stores timestamp per entity (agent, task)
3. On concurrent updates, newer timestamp wins
4. Full resync after WebSocket reconnection

### WebSocket Reconnection Flow

1. **Disconnection**: Frontend marks `wsConnected = false`
2. **Reconnection**: Exponential backoff (1s → 30s)
3. **Full Resync**: Backend sends complete state snapshot
4. **Timestamp Merge**: Frontend merges using conflict resolution

---

## Indexing Strategy

### Junction Table Indexes

```sql
-- Forward lookup: "What tasks does task X depend on?"
CREATE INDEX idx_task_dependencies_task ON task_dependencies(task_id)

-- Reverse lookup: "What tasks are blocked by task X?"
CREATE INDEX idx_task_dependencies_depends_on ON task_dependencies(depends_on_task_id)
```

### Task Number Index

```sql
-- Quick lookup by issue
CREATE INDEX idx_tasks_issue_number ON tasks(parent_issue_number)
```

---

## Data Consistency Guarantees

### Dual Storage Strategy

Dependencies are stored in **two places** for different use cases:

1. **`tasks.depends_on` (JSON string)**:
   - Simple queries: "Does this task have dependencies?"
   - Backward compatibility with existing code
   - Quick serialization for API responses

2. **`task_dependencies` (junction table)**:
   - Efficient graph traversal
   - Bidirectional queries (forward/reverse dependencies)
   - Foreign key constraints for referential integrity

### Update Protocol

All dependency modifications must update **both** storage locations atomically:

```python
# Example: add_task_dependency()
with transaction:
    # 1. Insert into junction table
    INSERT INTO task_dependencies (task_id, depends_on_task_id) VALUES (?, ?)

    # 2. Update JSON array in tasks table
    UPDATE tasks SET depends_on = ? WHERE id = ?
```

---

## Performance Characteristics

### Agent Pool Operations

- **Lookup**: O(1) - Dictionary access
- **Create**: O(1) - Dictionary insert + agent instantiation
- **Status Update**: O(1) - Dictionary update
- **Thread Contention**: Minimal - RLock with short critical sections

### Dependency Queries

- **Find Dependencies**: O(k) where k = number of dependencies (indexed lookup)
- **Find Dependents**: O(k) where k = number of dependents (indexed lookup)
- **Cycle Detection**: Not implemented (assumed acyclic task graphs)

### WebSocket Broadcasting

- **Broadcast Latency**: <10ms for typical pool size (≤10 agents)
- **Message Size**: ~200 bytes per message
- **Reconnection Overhead**: Full state sync for all agents + tasks

---

## API Contract Types

For external API compatibility, see TypeScript types in:

**File**: `/home/frankbria/projects/codeframe/web-ui/src/types/api.ts`

```typescript
export interface Task {
  id: string;
  task_number: string;
  title: string;
  description: string;
  status: WorkStatus;
  depends_on: string[];       // Task numbers, not IDs
  proposed_by: ProposedBy;
  created_at: ISODate;
  updated_at: ISODate;
  completed_at: ISODate | null;
}

export type WorkStatus =
  | 'pending'
  | 'assigned'
  | 'in_progress'
  | 'blocked'
  | 'completed'
  | 'failed';
```

**Note**: API uses task **numbers** (strings like "1.5.3") for human-readable dependencies, while internal database uses task **IDs** (integers) for referential integrity.

---

## Migration Notes

The multi-agent coordination feature was added incrementally without breaking changes:

1. **Schema Migration**: Added `task_dependencies` table via migration system
2. **Column Addition**: `tasks.depends_on` added with `DEFAULT '[]'`
3. **Backward Compatibility**: Existing code reading `depends_on` continues to work
4. **Index Creation**: Added junction table indexes for performance

No data migration required - new columns default to empty state.

---

## References

- **Implementation**: Sprint 4 (cf-21, cf-24)
- **Database Schema**: `/home/frankbria/projects/codeframe/codeframe/persistence/database.py`
- **Agent Pool**: `/home/frankbria/projects/codeframe/codeframe/agents/agent_pool_manager.py`
- **WebSocket**: `/home/frankbria/projects/codeframe/codeframe/ui/websocket_broadcasts.py`
- **Frontend Types**: `/home/frankbria/projects/codeframe/web-ui/src/types/agentState.ts`
- **API Types**: `/home/frankbria/projects/codeframe/web-ui/src/types/api.ts`
