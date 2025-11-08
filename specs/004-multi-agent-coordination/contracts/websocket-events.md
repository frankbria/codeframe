# WebSocket Event Contracts

## Overview

Multi-agent coordination in CodeFRAME uses WebSocket broadcasts to provide real-time updates to the dashboard. This document defines the event schemas for agent lifecycle, task assignments, and dependency management.

**File Location:** `/home/frankbria/projects/codeframe/codeframe/ui/websocket_broadcasts.py`

---

## Event Types

All events follow this base structure:

```python
{
    "type": str,           # Event type identifier
    "project_id": int,     # Project ID for routing
    "timestamp": str,      # ISO 8601 UTC timestamp (e.g., "2025-11-08T14:30:45.123Z")
    # ... type-specific fields
}
```

**Timestamp Format:** ISO 8601 with UTC timezone (`YYYY-MM-DDTHH:MM:SS.fffZ`)

---

## Agent Lifecycle Events

### agent_created

**Purpose:** Broadcast when a new agent is instantiated and added to the pool.

**Trigger:** `AgentPoolManager.create_agent()`

**Schema:**
```python
{
    "type": "agent_created",
    "project_id": int,
    "agent_id": str,          # e.g., "backend-worker-001"
    "agent_type": str,        # "backend" | "frontend" | "test"
    "status": "idle",         # Always "idle" on creation
    "tasks_completed": int,   # Always 0 on creation
    "timestamp": str          # ISO 8601 UTC
}
```

**Example:**
```json
{
    "type": "agent_created",
    "project_id": 1,
    "agent_id": "backend-worker-001",
    "agent_type": "backend",
    "status": "idle",
    "tasks_completed": 0,
    "timestamp": "2025-11-08T14:30:45.123Z"
}
```

**Function:**
```python
async def broadcast_agent_created(
    manager,
    project_id: int,
    agent_id: str,
    agent_type: str,
    tasks_completed: int = 0
) -> None
```

---

### agent_retired

**Purpose:** Broadcast when an agent is removed from the pool (retirement/cleanup).

**Trigger:** `AgentPoolManager.retire_agent()`

**Schema:**
```python
{
    "type": "agent_retired",
    "project_id": int,
    "agent_id": str,
    "tasks_completed": int,   # Total tasks completed by this agent
    "timestamp": str
}
```

**Example:**
```json
{
    "type": "agent_retired",
    "project_id": 1,
    "agent_id": "backend-worker-001",
    "tasks_completed": 5,
    "timestamp": "2025-11-08T15:45:30.456Z"
}
```

**Function:**
```python
async def broadcast_agent_retired(
    manager,
    project_id: int,
    agent_id: str,
    tasks_completed: int = 0
) -> None
```

---

### agent_status_changed

**Purpose:** Broadcast agent status transitions (idle ↔ working ↔ blocked).

**Trigger:** Agent state changes during task execution.

**Schema:**
```python
{
    "type": "agent_status_changed",
    "project_id": int,
    "agent_id": str,
    "status": str,            # "idle" | "working" | "blocked" | "offline"
    "current_task": {         # Optional: present if status = "working"
        "id": int,
        "title": str
    },
    "progress": int,          # Optional: 0-100 progress percentage
    "timestamp": str
}
```

**Example:**
```json
{
    "type": "agent_status_changed",
    "project_id": 1,
    "agent_id": "backend-worker-001",
    "status": "working",
    "current_task": {
        "id": 42,
        "title": "Create API endpoint for user registration"
    },
    "progress": 50,
    "timestamp": "2025-11-08T14:35:20.789Z"
}
```

**Function:**
```python
async def broadcast_agent_status(
    manager,
    project_id: int,
    agent_id: str,
    status: str,
    current_task_id: Optional[int] = None,
    current_task_title: Optional[str] = None,
    progress: Optional[int] = None
) -> None
```

---

## Task Assignment Events

### task_assigned

**Purpose:** Broadcast when a task is assigned to an agent.

**Trigger:** Task routing/assignment logic (e.g., `AgentPoolManager.mark_agent_busy()`)

**Schema:**
```python
{
    "type": "task_assigned",
    "project_id": int,
    "task_id": int,
    "agent_id": str,
    "task_title": str,        # Optional: for display
    "timestamp": str
}
```

**Example:**
```json
{
    "type": "task_assigned",
    "project_id": 1,
    "task_id": 42,
    "agent_id": "backend-worker-001",
    "task_title": "Create API endpoint",
    "timestamp": "2025-11-08T14:30:50.123Z"
}
```

**Function:**
```python
async def broadcast_task_assigned(
    manager,
    project_id: int,
    task_id: int,
    agent_id: str,
    task_title: Optional[str] = None
) -> None
```

---

### task_status_changed

**Purpose:** Broadcast task status transitions (pending → in_progress → completed/failed).

**Trigger:** `WorkerAgent.execute_task()`, `BackendWorkerAgent.update_task_status()`

**Schema:**
```python
{
    "type": "task_status_changed",
    "project_id": int,
    "task_id": int,
    "status": str,            # "pending" | "in_progress" | "completed" | "failed" | "blocked"
    "agent_id": str,          # Optional: agent executing the task
    "progress": int,          # Optional: 0-100 progress percentage
    "timestamp": str
}
```

**Example:**
```json
{
    "type": "task_status_changed",
    "project_id": 1,
    "task_id": 42,
    "status": "in_progress",
    "agent_id": "backend-worker-001",
    "progress": 25,
    "timestamp": "2025-11-08T14:31:00.000Z"
}
```

**Function:**
```python
async def broadcast_task_status(
    manager,
    project_id: int,
    task_id: int,
    status: str,
    agent_id: Optional[str] = None,
    progress: Optional[int] = None
) -> None
```

---

## Dependency Management Events

### task_blocked

**Purpose:** Broadcast when a task is blocked by dependencies and cannot proceed.

**Trigger:** Dependency resolution logic (when task has unmet dependencies)

**Schema:**
```python
{
    "type": "task_blocked",
    "project_id": int,
    "task_id": int,
    "blocked_by": List[int],  # List of task IDs blocking this task
    "blocked_count": int,     # Number of blockers (len(blocked_by))
    "task_title": str,        # Optional: for display
    "timestamp": str
}
```

**Example:**
```json
{
    "type": "task_blocked",
    "project_id": 1,
    "task_id": 45,
    "blocked_by": [42, 43],
    "blocked_count": 2,
    "task_title": "Create user dashboard component",
    "timestamp": "2025-11-08T14:32:15.456Z"
}
```

**Function:**
```python
async def broadcast_task_blocked(
    manager,
    project_id: int,
    task_id: int,
    blocked_by: List[int],
    task_title: Optional[str] = None
) -> None
```

---

### task_unblocked

**Purpose:** Broadcast when a task's dependencies are resolved and it can now proceed.

**Trigger:** Dependency resolution logic (when blocking task completes)

**Schema:**
```python
{
    "type": "task_unblocked",
    "project_id": int,
    "task_id": int,
    "unblocked_by": int,      # Optional: ID of task whose completion unblocked this one
    "task_title": str,        # Optional: for display
    "timestamp": str
}
```

**Example:**
```json
{
    "type": "task_unblocked",
    "project_id": 1,
    "task_id": 45,
    "unblocked_by": 42,
    "task_title": "Create user dashboard component",
    "timestamp": "2025-11-08T14:35:00.789Z"
}
```

**Function:**
```python
async def broadcast_task_unblocked(
    manager,
    project_id: int,
    task_id: int,
    unblocked_by: Optional[int] = None,
    task_title: Optional[str] = None
) -> None
```

---

## Additional Context Events

### test_result

**Purpose:** Broadcast test execution results (used by all worker agents).

**Schema:**
```python
{
    "type": "test_result",
    "project_id": int,
    "task_id": int,
    "status": str,            # "passed" | "failed" | "error" | "timeout" | "no_tests"
    "passed": int,
    "failed": int,
    "errors": int,
    "skipped": int,           # Optional
    "duration": float,        # Seconds
    "timestamp": str
}
```

**Function:**
```python
async def broadcast_test_result(
    manager,
    project_id: int,
    task_id: int,
    status: str,
    passed: int = 0,
    failed: int = 0,
    errors: int = 0,
    skipped: int = 0,
    duration: float = 0.0
) -> None
```

---

### activity_update

**Purpose:** Broadcast human-readable activity feed entries.

**Schema:**
```python
{
    "type": "activity_update",
    "project_id": int,
    "activity_type": str,     # "task" | "agent" | "test" | "commit" | etc.
    "message": str,           # Human-readable message
    "task_id": int,           # Optional
    "agent_id": str,          # Optional
    "timestamp": str
}
```

**Function:**
```python
async def broadcast_activity_update(
    manager,
    project_id: int,
    activity_type: str,
    agent_id: str,
    message_text: str,
    task_id: Optional[int] = None
) -> None
```

---

### correction_attempt

**Purpose:** Broadcast self-correction loop attempts (cf-43).

**Schema:**
```python
{
    "type": "correction_attempt",
    "project_id": int,
    "task_id": int,
    "attempt_number": int,    # 1-3
    "max_attempts": int,      # Usually 3
    "status": str,            # "in_progress" | "success" | "failed"
    "error_summary": str,     # Optional: for failed attempts
    "timestamp": str
}
```

**Function:**
```python
async def broadcast_correction_attempt(
    manager,
    project_id: int,
    task_id: int,
    attempt_number: int,
    max_attempts: int,
    status: str,
    error_summary: Optional[str] = None
) -> None
```

---

### progress_update

**Purpose:** Broadcast overall project progress.

**Schema:**
```python
{
    "type": "progress_update",
    "project_id": int,
    "completed": int,         # Number of completed tasks
    "total": int,             # Total number of tasks
    "percentage": int,        # 0-100
    "timestamp": str
}
```

**Function:**
```python
async def broadcast_progress_update(
    manager,
    project_id: int,
    completed: int,
    total: int,
    percentage: Optional[int] = None  # Auto-calculated if None
) -> None
```

---

## Connection Manager Interface

All broadcast functions use the `ConnectionManager` interface:

```python
class ConnectionManager:
    async def broadcast(self, message: Dict[str, Any]) -> None:
        """Broadcast message to all connected WebSocket clients."""
        pass
```

**Usage:**
```python
from codeframe.ui.websocket_broadcasts import broadcast_agent_created

await broadcast_agent_created(
    ws_manager,
    project_id=1,
    agent_id="backend-worker-001",
    agent_type="backend"
)
```

---

## Error Handling

All broadcast functions:
1. Wrap `manager.broadcast()` in try/except
2. Log errors at `ERROR` level
3. Never raise exceptions (fail silently to prevent task execution disruption)

**Example:**
```python
try:
    await manager.broadcast(message)
    logger.debug(f"Broadcast {event_type}: {details}")
except Exception as e:
    logger.error(f"Failed to broadcast {event_type}: {e}")
```

---

## Client-Side Integration

Dashboard clients should subscribe to these events:

```typescript
// Example React/TypeScript integration
websocket.onmessage = (event) => {
    const message = JSON.parse(event.data);

    switch (message.type) {
        case "agent_created":
            handleAgentCreated(message);
            break;
        case "agent_retired":
            handleAgentRetired(message);
            break;
        case "task_assigned":
            handleTaskAssigned(message);
            break;
        case "task_blocked":
            handleTaskBlocked(message);
            break;
        case "task_unblocked":
            handleTaskUnblocked(message);
            break;
        // ... handle other event types
    }
};
```

**See:** `web-ui/src/lib/websocketMessageMapper.ts` for full client-side mapping.

---

## Sprint Context

**Sprint 4 (cf-24):** Multi-Agent Coordination
**Sprint 5.2 (cf-45):** Real-Time Dashboard Updates (WebSocket integration)

**Dependencies:**
- ConnectionManager (WebSocket infrastructure)
- AgentPoolManager (cf-24)
- WorkerAgents (cf-41, cf-48, cf-49)

**Related Specs:**
- [Agent Pool API](./agent-pool-api.md)
- [Worker Agent Interface](./worker-agent-interface.md)
- Frontend State Management (CLAUDE.md: Phase 5.2)
