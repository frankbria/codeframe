# Context Management Data Model

**Feature**: 007-context-management
**Created**: 2025-11-14
**Status**: Planning (Phase 1)

## Overview

Data model for the Virtual Project context management system. Defines entities, relationships, validation rules, and state transitions for tiered memory management (HOT/WARM/COLD).

## Database Schema

### context_items Table

**Status**: ✅ **Already exists** in database.py:169-182

```sql
CREATE TABLE context_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    item_type TEXT NOT NULL CHECK(item_type IN ('TASK', 'CODE', 'ERROR', 'TEST_RESULT', 'PRD_SECTION')),
    content TEXT NOT NULL,
    importance_score REAL NOT NULL CHECK(importance_score >= 0.0 AND importance_score <= 1.0),
    tier TEXT NOT NULL DEFAULT 'WARM' CHECK(tier IN ('HOT', 'WARM', 'COLD')),
    access_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
);
```

**Indexes** (to be added for performance):
```sql
CREATE INDEX idx_context_agent_tier ON context_items(agent_id, tier);
CREATE INDEX idx_context_importance ON context_items(importance_score DESC);
CREATE INDEX idx_context_last_accessed ON context_items(last_accessed DESC);
```

### context_checkpoints Table (New)

**Status**: ❌ **Needs to be created**

For flash save checkpoint tracking:

```sql
CREATE TABLE context_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    checkpoint_data TEXT NOT NULL,  -- JSON serialized context state
    items_count INTEGER NOT NULL,
    items_archived INTEGER NOT NULL,
    hot_items_retained INTEGER NOT NULL,
    token_count INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
);
```

**Indexes**:
```sql
CREATE INDEX idx_checkpoints_agent_created ON context_checkpoints(agent_id, created_at DESC);
```

## Entities

### ContextItem

**Purpose**: Represents a single piece of context stored for an agent

**Fields**:
| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| id | int | Yes | Auto-increment PK | Unique identifier |
| agent_id | str | Yes | FK to agents | Agent that owns this context |
| item_type | str | Yes | Enum (5 values) | Type of context item |
| content | str | Yes | 1-100,000 chars | The actual context content |
| importance_score | float | Yes | 0.0-1.0 | Calculated importance score |
| tier | str | Yes | Enum (HOT/WARM/COLD) | Current tier assignment |
| access_count | int | No | >= 0 | Number of times accessed |
| created_at | datetime | Yes | Auto-set | Creation timestamp |
| last_accessed | datetime | Yes | Auto-update | Last access timestamp |

**Item Types**:
- `TASK`: Current or recent task descriptions
- `CODE`: Code snippets, file contents, or implementations
- `ERROR`: Error messages, stack traces, or failure logs
- `TEST_RESULT`: Test output, pass/fail status, or coverage reports
- `PRD_SECTION`: Relevant sections from PRD or requirements

**Type Weights** (for importance scoring):
```python
ITEM_TYPE_WEIGHTS = {
    'TASK': 1.0,        # Highest priority - current work
    'CODE': 0.8,        # High priority - implementation details
    'ERROR': 0.7,       # High priority - must track failures
    'TEST_RESULT': 0.6, # Medium priority - validation results
    'PRD_SECTION': 0.5  # Medium priority - requirements context
}
```

**Validation Rules**:
- `content` must be non-empty after strip()
- `importance_score` recalculated on each access
- `last_accessed` updated automatically on read
- `tier` reassigned when importance_score crosses thresholds

**State Transitions**:
```
PENDING (new item)
    ↓ (calculate_importance_score)
WARM (default tier)
    ↓ (score >= 0.8)
HOT (frequently accessed, recent)
    ↓ (score < 0.4)
COLD (stale, rarely accessed)
    ↓ (flash_save)
ARCHIVED (permanently moved to checkpoints)
```

### FlashSaveCheckpoint

**Purpose**: Snapshot of agent context during flash save operation

**Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | int | Yes | Unique identifier |
| agent_id | str | Yes | Agent that created checkpoint |
| checkpoint_data | str | Yes | JSON serialized context state |
| items_count | int | Yes | Total items before flash save |
| items_archived | int | Yes | Number of COLD items archived |
| hot_items_retained | int | Yes | Number of HOT items kept |
| token_count | int | Yes | Total tokens before flash save |
| created_at | datetime | Yes | Checkpoint timestamp |

**Checkpoint Data Structure** (JSON):
```json
{
  "agent_id": "backend-worker-001",
  "context_state": {
    "hot_items": [
      {"id": 123, "type": "TASK", "content": "...", "score": 0.95}
    ],
    "warm_items": [
      {"id": 124, "type": "CODE", "content": "...", "score": 0.65}
    ],
    "cold_items": [
      {"id": 125, "type": "ERROR", "content": "...", "score": 0.25}
    ]
  },
  "metrics": {
    "total_items": 150,
    "hot_count": 20,
    "warm_count": 75,
    "cold_count": 55,
    "total_tokens": 145000
  },
  "timestamp": "2025-11-14T11:30:00Z"
}
```

## Pydantic Models

### Request Models

```python
from pydantic import BaseModel, Field, validator
from typing import Literal
from datetime import datetime

class ContextItemCreate(BaseModel):
    """Request model for creating a context item."""
    item_type: Literal['TASK', 'CODE', 'ERROR', 'TEST_RESULT', 'PRD_SECTION']
    content: str = Field(..., min_length=1, max_length=100000)

    @validator('content')
    def content_not_empty(cls, v):
        if not v.strip():
            raise ValueError('Content cannot be empty or whitespace-only')
        return v.strip()

class ContextItemUpdate(BaseModel):
    """Request model for updating a context item."""
    content: str | None = Field(None, min_length=1, max_length=100000)
    importance_score: float | None = Field(None, ge=0.0, le=1.0)
    tier: Literal['HOT', 'WARM', 'COLD'] | None = None

class FlashSaveRequest(BaseModel):
    """Request model for initiating flash save."""
    force: bool = False  # Force flash save even if below 80% threshold
```

### Response Models

```python
class ContextItemResponse(BaseModel):
    """Response model for a single context item."""
    id: int
    agent_id: str
    item_type: str
    content: str
    importance_score: float
    tier: str
    access_count: int
    created_at: datetime
    last_accessed: datetime

    class Config:
        from_attributes = True

class ContextStatsResponse(BaseModel):
    """Response model for context statistics."""
    agent_id: str
    total_items: int
    hot_count: int
    warm_count: int
    cold_count: int
    total_tokens: int
    hot_tokens: int
    warm_tokens: int
    cold_tokens: int
    last_updated: datetime

class FlashSaveResponse(BaseModel):
    """Response model for flash save operation."""
    checkpoint_id: int
    agent_id: str
    items_count: int
    items_archived: int
    hot_items_retained: int
    token_count_before: int
    token_count_after: int
    reduction_percentage: float
    created_at: datetime
```

## Business Logic

### Importance Score Calculation

**Formula** (from research.md):
```python
def calculate_importance_score(
    item_type: str,
    created_at: datetime,
    access_count: int,
    last_accessed: datetime
) -> float:
    """
    Calculate importance score using hybrid approach:
    - Type weight (40%)
    - Recency decay (40%)
    - Access frequency (20%)
    """
    # Type weight component
    type_weight = ITEM_TYPE_WEIGHTS[item_type]

    # Age decay component (exponential decay, λ=0.5)
    age_days = (datetime.now(UTC) - created_at).total_seconds() / 86400
    age_decay = exp(-0.5 * age_days)

    # Access frequency component (log-normalized)
    access_boost = log(access_count + 1) / 10  # Cap at 1.0

    # Weighted combination
    score = (
        0.4 * type_weight +
        0.4 * age_decay +
        0.2 * min(access_boost, 1.0)
    )

    return min(max(score, 0.0), 1.0)  # Clamp to [0, 1]
```

### Tier Assignment Rules

```python
def assign_tier(importance_score: float) -> str:
    """Assign tier based on importance score."""
    if importance_score >= 0.8:
        return 'HOT'
    elif importance_score >= 0.4:
        return 'WARM'
    else:
        return 'COLD'
```

**Tier Meanings**:
- **HOT** (>= 0.8): Always loaded into agent context, critical recent work
- **WARM** (0.4-0.8): Loaded on-demand when referenced, supporting context
- **COLD** (< 0.4): Archived, only loaded if explicitly requested, stale content

### Flash Save Trigger

```python
async def should_flash_save(agent_id: str, current_tokens: int) -> bool:
    """Determine if flash save should be triggered."""
    TOKEN_LIMIT = 180000  # Claude's context window
    FLASH_SAVE_THRESHOLD = 0.80  # 80% of limit

    return current_tokens >= (TOKEN_LIMIT * FLASH_SAVE_THRESHOLD)
```

## Relationships

```
Agent (1) ──── (many) ContextItem
  │
  └── (many) FlashSaveCheckpoint

ContextItem:
  - Belongs to one Agent (agent_id FK)
  - No relationships to other entities
  - Isolated per-agent context storage

FlashSaveCheckpoint:
  - Belongs to one Agent (agent_id FK)
  - References ContextItems via checkpoint_data JSON
  - Historical record, no active relationships
```

## Query Patterns

### Load Hot Context (Most Common)

```sql
SELECT * FROM context_items
WHERE agent_id = ? AND tier = 'HOT'
ORDER BY importance_score DESC, last_accessed DESC
LIMIT 100;
```

### Get Context Stats

```sql
SELECT
    tier,
    COUNT(*) as count,
    SUM(LENGTH(content)) as total_chars
FROM context_items
WHERE agent_id = ?
GROUP BY tier;
```

### Archive Cold Items (Flash Save)

```sql
-- Mark COLD items as archived
UPDATE context_items
SET tier = 'ARCHIVED'
WHERE agent_id = ? AND tier = 'COLD';

-- Create checkpoint record
INSERT INTO context_checkpoints (agent_id, checkpoint_data, items_count, ...)
VALUES (?, ?, ?, ...);
```

### Tier Reassignment (Periodic)

```sql
-- Update tiers based on recalculated importance scores
UPDATE context_items
SET
    tier = CASE
        WHEN importance_score >= 0.8 THEN 'HOT'
        WHEN importance_score >= 0.4 THEN 'WARM'
        ELSE 'COLD'
    END,
    last_accessed = CURRENT_TIMESTAMP
WHERE agent_id = ?;
```

## Migration Requirements

### Migration 004: Add context_checkpoints Table

```python
def apply(conn):
    cursor = conn.cursor()

    # Create context_checkpoints table
    cursor.execute("""
        CREATE TABLE context_checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            checkpoint_data TEXT NOT NULL,
            items_count INTEGER NOT NULL,
            items_archived INTEGER NOT NULL,
            hot_items_retained INTEGER NOT NULL,
            token_count INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
        )
    """)

    # Add indexes
    cursor.execute("""
        CREATE INDEX idx_checkpoints_agent_created
        ON context_checkpoints(agent_id, created_at DESC)
    """)

    conn.commit()
```

### Migration 005: Add Indexes to context_items

```python
def apply(conn):
    cursor = conn.cursor()

    # Add performance indexes
    cursor.execute("""
        CREATE INDEX idx_context_agent_tier
        ON context_items(agent_id, tier)
    """)

    cursor.execute("""
        CREATE INDEX idx_context_importance
        ON context_items(importance_score DESC)
    """)

    cursor.execute("""
        CREATE INDEX idx_context_last_accessed
        ON context_items(last_accessed DESC)
    """)

    conn.commit()
```

## Validation Rules Summary

| Rule | Enforcement | Error Message |
|------|-------------|---------------|
| content non-empty | Pydantic validator | "Content cannot be empty or whitespace-only" |
| content <= 100k chars | Pydantic Field | "Content exceeds maximum length of 100000 characters" |
| importance_score in [0,1] | Database CHECK + Pydantic | "Importance score must be between 0.0 and 1.0" |
| tier in enum | Database CHECK + Pydantic | "Tier must be one of: HOT, WARM, COLD" |
| item_type in enum | Database CHECK + Pydantic | "Invalid item type, must be one of: TASK, CODE, ERROR, TEST_RESULT, PRD_SECTION" |

## Performance Considerations

**Database Optimizations**:
- Indexes on `(agent_id, tier)` for fast hot context loading
- Index on `importance_score DESC` for tier reassignment queries
- Index on `last_accessed DESC` for age-based sorting

**Query Limits**:
- Hot context load: LIMIT 100 items (prevent unbounded queries)
- Checkpoint history: Keep last 10 checkpoints per agent (periodic cleanup)
- Tier reassignment: Batch updates every 5 minutes (not on every access)

**Token Counting Cache**:
- Cache token counts for unchanged content (content hash as key)
- Invalidate cache on content modification
- Trade-off: 10% memory increase for 90% token count speedup

## References

- **Research**: [research.md](research.md) - Importance scoring algorithms
- **Database Schema**: codeframe/persistence/database.py:169-182
- **Constitution**: Principle III (Context Efficiency)
- **Feature Spec**: [spec.md](spec.md)
