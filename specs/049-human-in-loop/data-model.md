# Data Model: Human-in-the-Loop

## Overview

This document specifies the data structures, database schema, API contracts, and WebSocket messages for the human-in-the-loop blocker system in CodeFRAME.

## Database Schema

### blockers table (existing, no migration needed)

The blockers table already exists in production (`codeframe/persistence/database.py` lines 140-152):

```sql
CREATE TABLE IF NOT EXISTS blockers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,                      -- Associated task (nullable for agent-level blockers)
    severity TEXT CHECK(severity IN ('sync', 'async')),  -- 'sync' (critical) or 'async' (clarification)
    reason TEXT,                          -- Deprecated: brief blocker context (use question instead)
    question TEXT,                        -- Question for user (max 2000 chars)
    resolution TEXT,                      -- Deprecated: use answer instead
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,                -- When user submitted answer (NULL until resolved)
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);
```

### Required Schema Updates

The existing schema needs the following updates for 049-human-in-loop:

1. **Add `agent_id` column** (required):
```sql
ALTER TABLE blockers ADD COLUMN agent_id TEXT NOT NULL DEFAULT '';
```

2. **Add `answer` column** (required):
```sql
ALTER TABLE blockers ADD COLUMN answer TEXT;  -- Max 5000 chars, NULL until resolved
```

3. **Add `status` column** (required):
```sql
ALTER TABLE blockers ADD COLUMN status TEXT NOT NULL DEFAULT 'PENDING'
    CHECK(status IN ('PENDING', 'RESOLVED', 'EXPIRED'));
```

4. **Rename `severity` to `blocker_type`** (required):
```sql
-- This requires a table rebuild in SQLite
-- Migration script will handle this transformation
```

5. **Add indexes** (performance optimization):
```sql
CREATE INDEX IF NOT EXISTS idx_blockers_status_created
    ON blockers(status, created_at);  -- For stale blocker queries

CREATE INDEX IF NOT EXISTS idx_blockers_agent_status
    ON blockers(agent_id, status);    -- For agent polling queries
```

### Target Schema (after migration)

```sql
CREATE TABLE IF NOT EXISTS blockers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,           -- Agent that created blocker (e.g., 'backend-worker-001')
    project_id INTEGER NOT NULL,      -- Project this blocker belongs to
    task_id INTEGER,                  -- Associated task (nullable for agent-level blockers)
    blocker_type TEXT NOT NULL,       -- 'SYNC' (critical) or 'ASYNC' (clarification)
    question TEXT NOT NULL,           -- Question for user (max 2000 chars)
    answer TEXT,                      -- User's answer (max 5000 chars, NULL until resolved)
    status TEXT NOT NULL DEFAULT 'PENDING',  -- 'PENDING' | 'RESOLVED' | 'EXPIRED'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,            -- When user submitted answer (NULL until resolved)
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_blockers_status_created
    ON blockers(status, created_at);

CREATE INDEX IF NOT EXISTS idx_blockers_agent_status
    ON blockers(agent_id, status);

CREATE INDEX IF NOT EXISTS idx_blockers_project_status
    ON blockers(project_id, status);
```

**Migration Strategy**: Create migration script `migration_003_update_blockers_schema.py` to:
1. Create new temp table with target schema
2. Copy data: `severity` → `blocker_type`, generate `agent_id` from task assignments
3. Drop old table, rename temp table
4. Create indexes

## Python Data Models

### Enums

```python
# codeframe/core/models.py

from enum import Enum

class BlockerType(str, Enum):
    """Type of blocker requiring human intervention."""
    SYNC = "SYNC"      # Critical blocker - agent pauses immediately
    ASYNC = "ASYNC"    # Clarification request - agent continues work

class BlockerStatus(str, Enum):
    """Current status of a blocker."""
    PENDING = "PENDING"      # Awaiting user response
    RESOLVED = "RESOLVED"    # User has provided answer
    EXPIRED = "EXPIRED"      # Blocker timed out (24h default)
```

### Pydantic Models

```python
# codeframe/core/models.py

from pydantic import BaseModel, Field
from datetime import datetime

class Blocker(BaseModel):
    """Database model for a blocker."""
    id: int
    agent_id: str
    task_id: int | None
    blocker_type: BlockerType
    question: str = Field(..., max_length=2000)
    answer: str | None = Field(None, max_length=5000)
    status: BlockerStatus
    created_at: datetime
    resolved_at: datetime | None

    class Config:
        from_attributes = True  # For SQLAlchemy/SQLite compatibility

class BlockerCreate(BaseModel):
    """Request model for creating a blocker."""
    agent_id: str
    task_id: int | None
    blocker_type: BlockerType
    question: str = Field(..., min_length=1, max_length=2000)

class BlockerResolve(BaseModel):
    """Request model for resolving a blocker."""
    answer: str = Field(..., min_length=1, max_length=5000)

class BlockerListResponse(BaseModel):
    """Response model for listing blockers."""
    blockers: list[Blocker]
    total: int
    pending_count: int
    sync_count: int
```

## TypeScript Types

### Frontend Data Models

```typescript
// web-ui/src/types/blocker.ts

export type BlockerType = 'SYNC' | 'ASYNC';
export type BlockerStatus = 'PENDING' | 'RESOLVED' | 'EXPIRED';

export interface Blocker {
  id: number;
  agent_id: string;
  task_id: number | null;
  blocker_type: BlockerType;
  question: string;
  answer: string | null;
  status: BlockerStatus;
  created_at: string;  // ISO 8601
  resolved_at: string | null;  // ISO 8601

  // Computed fields (from API joins)
  agent_name?: string;
  task_title?: string;
  time_waiting_ms?: number;
}

export interface BlockerCreateRequest {
  agent_id: string;
  task_id: number | null;
  blocker_type: BlockerType;
  question: string;
}

export interface BlockerResolveRequest {
  answer: string;
}

export interface BlockerListResponse {
  blockers: Blocker[];
  total: number;
  pending_count: number;
  sync_count: number;
}
```

## WebSocket Message Types

### blocker_created

Sent when agent creates a new blocker:

```json
{
  "type": "blocker_created",
  "blocker_id": 123,
  "agent_id": "backend-worker-001",
  "task_id": 456,
  "blocker_type": "SYNC",
  "question": "Should I use SQLite or PostgreSQL for this feature?",
  "created_at": "2025-11-08T12:34:56Z"
}
```

### blocker_resolved

Sent when user resolves a blocker:

```json
{
  "type": "blocker_resolved",
  "blocker_id": 123,
  "answer": "Use SQLite to match existing codebase",
  "resolved_at": "2025-11-08T12:45:30Z"
}
```

### agent_resumed

Sent when agent resumes work after blocker resolution:

```json
{
  "type": "agent_resumed",
  "agent_id": "backend-worker-001",
  "task_id": 456,
  "blocker_id": 123,
  "resumed_at": "2025-11-08T12:45:35Z"
}
```

## State Transitions

```
                  create_blocker()
[Agent Working] ─────────────────> [PENDING Blocker]
                                         │
                                         │ user resolves
                                         ├──────────────> [RESOLVED Blocker]
                                         │                      │
                                         │                      │ agent polls
                                         │                      v
                                         │               [Agent Resumed]
                                         │
                                         │ 24h timeout
                                         └──────────────> [EXPIRED Blocker]
                                                               │
                                                               v
                                                         [Task FAILED]
```

**State Rules**:
- PENDING → RESOLVED: User submits answer via API
- PENDING → EXPIRED: Cron job expires blockers >24h old
- RESOLVED/EXPIRED are terminal states (no further transitions)

## Database Operations

### Create Blocker

```python
# codeframe/persistence/database.py

async def create_blocker(
    self,
    agent_id: str,
    project_id: int,
    task_id: int | None,
    blocker_type: BlockerType,
    question: str
) -> int:
    """Create new blocker, return blocker_id."""
    cursor = self.conn.cursor()
    cursor.execute(
        """INSERT INTO blockers (agent_id, project_id, task_id, blocker_type, question, status)
           VALUES (?, ?, ?, ?, ?, 'PENDING')""",
        (agent_id, project_id, task_id, blocker_type.value, question)
    )
    self.conn.commit()
    return cursor.lastrowid
```

**Complexity**: O(1) - single INSERT

### Resolve Blocker

```python
async def resolve_blocker(self, blocker_id: int, answer: str) -> bool:
    """Resolve blocker with answer. Returns False if already resolved."""
    cursor = self.conn.cursor()
    cursor.execute(
        """UPDATE blockers
           SET answer = ?, status = 'RESOLVED', resolved_at = CURRENT_TIMESTAMP
           WHERE id = ? AND status = 'PENDING'""",
        (answer, blocker_id)
    )
    self.conn.commit()
    return cursor.rowcount > 0  # False if already resolved or not found
```

**Complexity**: O(1) - single UPDATE with WHERE clause

### Check for Pending Blockers (Agent Polling)

```python
async def get_pending_blocker(self, agent_id: str) -> Blocker | None:
    """Get oldest pending blocker for agent, if any."""
    cursor = self.conn.cursor()
    cursor.execute(
        """SELECT * FROM blockers
           WHERE agent_id = ? AND status = 'PENDING'
           ORDER BY created_at ASC LIMIT 1""",
        (agent_id,)
    )
    row = cursor.fetchone()
    return Blocker(**dict(row)) if row else None
```

**Complexity**: O(log N) - index scan on `(agent_id, status)`

### Expire Stale Blockers (Cron Job)

```python
async def expire_stale_blockers(self, hours: int = 24) -> list[int]:
    """Expire blockers pending >N hours, return blocker IDs."""
    cursor = self.conn.cursor()
    cursor.execute(
        """UPDATE blockers
           SET status = 'EXPIRED'
           WHERE status = 'PENDING'
             AND datetime(created_at) < datetime('now', '-{} hours')
           RETURNING id""".format(hours)
    )
    self.conn.commit()
    return [row[0] for row in cursor.fetchall()]
```

**Complexity**: O(N) for N stale blockers (batched hourly via cron)

### List Blockers with Enrichment

```python
async def list_blockers(
    self,
    project_id: int,
    status: BlockerStatus | None = None
) -> BlockerListResponse:
    """List blockers with agent/task info joined."""
    cursor = self.conn.cursor()

    # Build query with optional status filter
    query = """
        SELECT
            b.*,
            a.type as agent_name,
            t.title as task_title,
            (julianday('now') - julianday(b.created_at)) * 86400000 as time_waiting_ms
        FROM blockers b
        LEFT JOIN agents a ON b.agent_id = a.id
        LEFT JOIN tasks t ON b.task_id = t.id
        WHERE b.project_id = ?
    """
    params = [project_id]

    if status:
        query += " AND b.status = ?"
        params.append(status.value)

    query += " ORDER BY b.created_at DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    blockers = [Blocker(**dict(row)) for row in rows]
    pending_count = sum(1 for b in blockers if b.status == BlockerStatus.PENDING)
    sync_count = sum(1 for b in blockers if b.blocker_type == BlockerType.SYNC)

    return BlockerListResponse(
        blockers=blockers,
        total=len(blockers),
        pending_count=pending_count,
        sync_count=sync_count
    )
```

**Complexity**: O(M) for M active blockers (typically <50)

## API Response Formats

### GET /api/blockers

**Query Parameters**:
- `project_id` (required): Filter by project
- `status` (optional): Filter by status (PENDING, RESOLVED, EXPIRED)

**Response (200 OK)**:
```json
{
  "blockers": [
    {
      "id": 123,
      "agent_id": "backend-worker-001",
      "agent_name": "Backend Worker #1",
      "task_id": 456,
      "task_title": "Implement user authentication",
      "blocker_type": "SYNC",
      "question": "Should we use JWT or session-based auth?",
      "answer": null,
      "status": "PENDING",
      "created_at": "2025-11-08T12:34:56Z",
      "resolved_at": null,
      "time_waiting_ms": 1234567
    }
  ],
  "total": 1,
  "pending_count": 1,
  "sync_count": 1
}
```

### POST /api/blockers/:id/resolve

**Request**:
```json
{
  "answer": "Use JWT for stateless API authentication"
}
```

**Response (200 OK - success)**:
```json
{
  "blocker_id": 123,
  "status": "RESOLVED",
  "resolved_at": "2025-11-08T12:45:30Z"
}
```

**Response (409 Conflict - already resolved)**:
```json
{
  "error": "Blocker already resolved",
  "blocker_id": 123,
  "resolved_at": "2025-11-08T12:44:00Z"
}
```

**Response (404 Not Found)**:
```json
{
  "error": "Blocker not found",
  "blocker_id": 123
}
```

## Performance Characteristics

| Operation | Time Complexity | Notes |
|-----------|----------------|-------|
| Blocker creation | O(1) | Single INSERT |
| Blocker resolution | O(1) | Single UPDATE with WHERE |
| Agent polling | O(log N) | Index scan on `(agent_id, status)` |
| Stale blocker expiration | O(N) | For N stale blockers (batched hourly) |
| Dashboard list | O(M) | For M active blockers (typically <50) |

**Index Coverage**:
- `idx_blockers_agent_status` on `(agent_id, status)` - covers agent polling
- `idx_blockers_status_created` on `(status, created_at)` - covers stale blocker queries

**Typical Load**:
- Active blockers: <10 per project
- Polling frequency: Every 5s per agent (3-5 agents)
- List queries: <1/min (user-initiated)

## Migration Strategy

### Migration 003: Update Blockers Schema

**File**: `codeframe/persistence/migrations/migration_003_update_blockers_schema.py`

```python
from codeframe.persistence.migrations.base import Migration

class Migration003(Migration):
    """Update blockers table for 049-human-in-loop feature."""

    version = 3
    description = "Add agent_id, answer, status to blockers table"

    def upgrade(self, conn):
        cursor = conn.cursor()

        # 1. Create new table with target schema
        cursor.execute("""
            CREATE TABLE blockers_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                task_id INTEGER,
                blocker_type TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
        """)

        # 2. Copy existing data, mapping old columns to new
        cursor.execute("""
            INSERT INTO blockers_new
                (id, agent_id, task_id, blocker_type, question, status, created_at, resolved_at)
            SELECT
                b.id,
                COALESCE(t.assigned_to, 'unknown-agent') as agent_id,
                b.task_id,
                UPPER(b.severity) as blocker_type,
                COALESCE(b.question, b.reason, 'No question provided') as question,
                CASE
                    WHEN b.resolved_at IS NOT NULL THEN 'RESOLVED'
                    ELSE 'PENDING'
                END as status,
                b.created_at,
                b.resolved_at
            FROM blockers b
            LEFT JOIN tasks t ON b.task_id = t.id
        """)

        # 3. Drop old table
        cursor.execute("DROP TABLE blockers")

        # 4. Rename new table
        cursor.execute("ALTER TABLE blockers_new RENAME TO blockers")

        # 5. Create indexes
        cursor.execute("""
            CREATE INDEX idx_blockers_status_created
            ON blockers(status, created_at)
        """)
        cursor.execute("""
            CREATE INDEX idx_blockers_agent_status
            ON blockers(agent_id, status)
        """)

        conn.commit()

    def downgrade(self, conn):
        # Not supported - data loss would occur
        raise NotImplementedError("Cannot downgrade blockers schema migration")

migration = Migration003()
```

**Data Mapping**:
- `severity` → `blocker_type` (uppercase transformation)
- `reason`/`question` → `question` (prefer question, fallback to reason)
- Derive `agent_id` from `tasks.assigned_to` (fallback: 'unknown-agent')
- Infer `status` from `resolved_at` (NULL → PENDING, not NULL → RESOLVED)

## Validation Rules

### Question Validation
- **Min length**: 1 character
- **Max length**: 2000 characters
- **Required**: Cannot be NULL or empty string
- **Trimming**: Leading/trailing whitespace removed before storage

### Answer Validation
- **Min length**: 1 character (when provided)
- **Max length**: 5000 characters
- **Required**: Only when resolving blocker
- **Trimming**: Leading/trailing whitespace removed before storage

### Agent ID Validation
- **Format**: `{type}-{number}` (e.g., "backend-worker-001")
- **Required**: Cannot be NULL or empty string
- **Foreign key**: Must match existing agent in `agents` table

### Task ID Validation
- **Nullable**: Can be NULL for agent-level blockers
- **Foreign key**: When provided, must match existing task in `tasks` table
- **Cascade delete**: Blocker deleted if referenced task is deleted

## Error Handling

### Concurrency Scenarios

**Scenario 1: Duplicate Resolution**
```python
# User 1 resolves blocker
await resolve_blocker(123, "Answer A")  # Returns True

# User 2 tries to resolve same blocker (race condition)
result = await resolve_blocker(123, "Answer B")  # Returns False
```
**Behavior**: Second resolution fails silently (returns False). First resolution wins.

**Scenario 2: Agent Polls During Resolution**
```python
# Agent polling loop
blocker = await get_pending_blocker("agent-001")  # Returns blocker 123
# ... user resolves blocker 123 here ...
blocker_check = await get_pending_blocker("agent-001")  # Returns None
```
**Behavior**: Agent sees blocker disappear from pending queue. Next poll gets answer.

### Timeout Handling

**Expiration Cron Job** (runs hourly):
```python
expired_ids = await expire_stale_blockers(hours=24)
for blocker_id in expired_ids:
    blocker = await get_blocker(blocker_id)
    if blocker.task_id:
        await update_task(blocker.task_id, {"status": TaskStatus.FAILED})
    await broadcast_websocket({
        "type": "blocker_expired",
        "blocker_id": blocker_id,
        "task_id": blocker.task_id
    })
```

## Testing Strategy

### Unit Tests

**File**: `tests/test_blockers.py`

```python
def test_create_blocker():
    """Test creating a blocker."""
    blocker_id = db.create_blocker(
        agent_id="backend-worker-001",
        task_id=1,
        blocker_type=BlockerType.SYNC,
        question="How should I implement X?"
    )
    assert blocker_id > 0
    blocker = db.get_blocker(blocker_id)
    assert blocker.status == BlockerStatus.PENDING

def test_resolve_blocker():
    """Test resolving a blocker."""
    blocker_id = db.create_blocker(...)
    success = db.resolve_blocker(blocker_id, "Do it this way")
    assert success is True
    blocker = db.get_blocker(blocker_id)
    assert blocker.status == BlockerStatus.RESOLVED
    assert blocker.answer == "Do it this way"

def test_resolve_blocker_twice():
    """Test resolving already-resolved blocker fails."""
    blocker_id = db.create_blocker(...)
    db.resolve_blocker(blocker_id, "Answer 1")
    success = db.resolve_blocker(blocker_id, "Answer 2")
    assert success is False  # Second resolution fails
    blocker = db.get_blocker(blocker_id)
    assert blocker.answer == "Answer 1"  # First answer wins

def test_expire_stale_blockers():
    """Test expiring old blockers."""
    # Create blocker with old timestamp (manual SQL)
    # Run expiration job
    expired = db.expire_stale_blockers(hours=24)
    assert len(expired) == 1
```

### Integration Tests

**File**: `tests/integration/test_blocker_workflow.py`

```python
async def test_blocker_workflow_e2e():
    """Test complete blocker lifecycle."""
    # 1. Agent creates blocker
    blocker_id = await agent.create_blocker("Question?")
    assert blocker_id > 0

    # 2. User sees blocker in dashboard
    response = await client.get("/api/blockers?project_id=1")
    assert response.json()["pending_count"] == 1

    # 3. User resolves blocker
    response = await client.post(
        f"/api/blockers/{blocker_id}/resolve",
        json={"answer": "Answer"}
    )
    assert response.status_code == 200

    # 4. Agent polls and resumes
    blocker = await agent.poll_blocker()
    assert blocker.answer == "Answer"
    await agent.resume_work()
```

---

**Document Version**: 1.0
**Last Updated**: 2025-11-08
**Feature**: 049-human-in-loop
**Sprint**: Sprint 6
