# Data Model: Review & Polish (Sprint 10)

**Feature**: 015-review-polish
**Date**: 2025-11-21

## Overview

This document defines the data models for Sprint 10 components: Review Agent, Quality Gates, Checkpoints, and Metrics Tracking. Models follow existing CodeFRAME patterns (Pydantic for validation, SQLite for persistence).

---

## Database Schema Changes

### New Tables

#### 1. `code_reviews` - Code review findings

```sql
CREATE TABLE code_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,               -- Review agent that performed review
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,              -- Relative path from project root
    line_number INTEGER,                  -- NULL for file-level findings
    severity TEXT NOT NULL CHECK(severity IN ('critical', 'high', 'medium', 'low', 'info')),
    category TEXT NOT NULL CHECK(category IN ('security', 'performance', 'quality', 'maintainability', 'style')),
    message TEXT NOT NULL,                -- Description of the issue
    recommendation TEXT,                  -- How to fix it
    code_snippet TEXT,                    -- Offending code (for context)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_reviews_task ON code_reviews(task_id);
CREATE INDEX idx_reviews_severity ON code_reviews(severity, created_at);
CREATE INDEX idx_reviews_project ON code_reviews(project_id, created_at);
```

**Purpose**: Store findings from Review Agent code analysis
**Relationships**: Many reviews per task (one-to-many)
**Validation**: Severity and category must be valid enum values

---

#### 2. `token_usage` - Token tracking per LLM call

```sql
CREATE TABLE token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,  -- NULL for non-task calls
    agent_id TEXT NOT NULL,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,             -- e.g., "claude-sonnet-4-5"
    input_tokens INTEGER NOT NULL CHECK(input_tokens >= 0),
    output_tokens INTEGER NOT NULL CHECK(output_tokens >= 0),
    estimated_cost_usd REAL NOT NULL CHECK(estimated_cost_usd >= 0),
    actual_cost_usd REAL,                 -- From API billing (if available)
    call_type TEXT CHECK(call_type IN ('task_execution', 'code_review', 'coordination', 'other')),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_token_usage_agent ON token_usage(agent_id, timestamp);
CREATE INDEX idx_token_usage_project ON token_usage(project_id, timestamp);
CREATE INDEX idx_token_usage_task ON token_usage(task_id);
```

**Purpose**: Track token usage for cost analysis and optimization
**Relationships**: Optional many tokens per task (may have non-task calls)
**Validation**: Tokens and costs must be non-negative

---

#### 3. `checkpoint_snapshots` - Enhanced checkpoint metadata

```sql
-- Note: checkpoints table already exists (database.py:236-248)
-- This extends it with additional fields

ALTER TABLE checkpoints ADD COLUMN name TEXT;  -- User-friendly name
ALTER TABLE checkpoints ADD COLUMN description TEXT;  -- Optional notes
ALTER TABLE checkpoints ADD COLUMN database_backup_path TEXT NOT NULL;
ALTER TABLE checkpoints ADD COLUMN context_snapshot_path TEXT NOT NULL;
ALTER TABLE checkpoints ADD COLUMN metadata JSON;  -- Stats: tasks_completed, agents_active, etc.

CREATE INDEX idx_checkpoints_project ON checkpoints(project_id, created_at DESC);
```

**Purpose**: Store checkpoint metadata for restore operations
**Relationships**: Many checkpoints per project (one-to-many)
**Validation**: Paths must exist before marking checkpoint as valid

---

### Modified Tables

#### `tasks` - Add quality gate tracking

```sql
ALTER TABLE tasks ADD COLUMN quality_gate_status TEXT
    CHECK(quality_gate_status IN ('pending', 'running', 'passed', 'failed'))
    DEFAULT 'pending';

ALTER TABLE tasks ADD COLUMN quality_gate_failures JSON;
    -- Structure: [{"gate": "tests", "reason": "3 tests failed", "details": "..."}]

ALTER TABLE tasks ADD COLUMN requires_human_approval BOOLEAN DEFAULT FALSE;
    -- True for risky changes (schema migrations, API changes)
```

**Purpose**: Track quality gate enforcement per task
**New Fields**:
- `quality_gate_status`: Current state of quality checks
- `quality_gate_failures`: Detailed failure information for debugging
- `requires_human_approval`: Flag for manual approval requirement

---

## Pydantic Models

### 1. CodeReview

```python
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime

class Severity(str, Enum):
    """Code review finding severity levels."""
    CRITICAL = "critical"  # Must fix before completion
    HIGH = "high"          # Should fix before completion
    MEDIUM = "medium"      # Should fix eventually
    LOW = "low"            # Nice to fix
    INFO = "info"          # Informational only

class ReviewCategory(str, Enum):
    """Code review finding categories."""
    SECURITY = "security"          # Security vulnerabilities
    PERFORMANCE = "performance"    # Performance issues
    QUALITY = "quality"            # Code quality problems
    MAINTAINABILITY = "maintainability"  # Hard to maintain code
    STYLE = "style"                # Style/formatting issues

class CodeReview(BaseModel):
    """Code review finding from Review Agent."""
    id: Optional[int] = None
    task_id: int
    agent_id: str
    project_id: int
    file_path: str = Field(..., description="Relative path from project root")
    line_number: Optional[int] = Field(None, description="Line number, None for file-level")
    severity: Severity
    category: ReviewCategory
    message: str = Field(..., min_length=10, description="Description of the issue")
    recommendation: Optional[str] = Field(None, description="How to fix it")
    code_snippet: Optional[str] = Field(None, description="Offending code for context")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True

    @property
    def is_blocking(self) -> bool:
        """Whether this finding should block task completion."""
        return self.severity in [Severity.CRITICAL, Severity.HIGH]
```

---

### 2. TokenUsage

```python
class CallType(str, Enum):
    """Type of LLM call for categorization."""
    TASK_EXECUTION = "task_execution"
    CODE_REVIEW = "code_review"
    COORDINATION = "coordination"
    OTHER = "other"

class TokenUsage(BaseModel):
    """Token usage record for a single LLM call."""
    id: Optional[int] = None
    task_id: Optional[int] = None  # None for non-task calls
    agent_id: str
    project_id: int
    model_name: str = Field(..., description="e.g., claude-sonnet-4-5")
    input_tokens: int = Field(..., ge=0)
    output_tokens: int = Field(..., ge=0)
    estimated_cost_usd: float = Field(..., ge=0.0)
    actual_cost_usd: Optional[float] = Field(None, ge=0.0)
    call_type: CallType = CallType.OTHER
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True

    @property
    def total_tokens(self) -> int:
        """Total tokens (input + output)."""
        return self.input_tokens + self.output_tokens

    @classmethod
    def calculate_cost(
        cls,
        model_name: str,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """Calculate estimated cost in USD."""
        # Pricing as of 2025-11
        pricing = {
            "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
            "claude-opus-4": {"input": 15.00, "output": 75.00},
            "claude-haiku-4": {"input": 0.80, "output": 4.00},
        }

        if model_name not in pricing:
            raise ValueError(f"Unknown model: {model_name}")

        prices = pricing[model_name]
        cost = (
            (input_tokens * prices["input"] / 1_000_000) +
            (output_tokens * prices["output"] / 1_000_000)
        )
        return round(cost, 6)  # 6 decimal places for precision
```

---

### 3. Checkpoint

```python
from pathlib import Path

class CheckpointMetadata(BaseModel):
    """Metadata stored in checkpoint for quick inspection."""
    project_id: int
    phase: str  # discovery, planning, active, review, complete
    tasks_completed: int
    tasks_total: int
    agents_active: list[str]
    last_task_completed: Optional[str] = None
    context_items_count: int
    total_cost_usd: float

class Checkpoint(BaseModel):
    """Project checkpoint for restore operations."""
    id: Optional[int] = None
    project_id: int
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    trigger: str = Field(..., description="manual, auto, phase_transition")
    git_commit: str = Field(..., min_length=7, max_length=40, description="Git commit SHA")
    database_backup_path: str = Field(..., description="Path to .sqlite backup")
    context_snapshot_path: str = Field(..., description="Path to context JSON")
    metadata: CheckpointMetadata
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def checkpoint_dir(self) -> Path:
        """Directory containing checkpoint files."""
        return Path(f".codeframe/checkpoints/checkpoint-{self.id:03d}")

    def validate_files_exist(self) -> bool:
        """Check if all checkpoint files exist."""
        db_path = Path(self.database_backup_path)
        context_path = Path(self.context_snapshot_path)
        return db_path.exists() and context_path.exists()
```

---

### 4. QualityGateResult

```python
class QualityGateType(str, Enum):
    """Types of quality gates."""
    TESTS = "tests"
    TYPE_CHECK = "type_check"
    COVERAGE = "coverage"
    CODE_REVIEW = "code_review"
    LINTING = "linting"

class QualityGateFailure(BaseModel):
    """Individual quality gate failure."""
    gate: QualityGateType
    reason: str = Field(..., min_length=5)
    details: Optional[str] = None  # Full error output
    severity: Severity = Severity.HIGH

class QualityGateResult(BaseModel):
    """Result of running quality gates for a task."""
    task_id: int
    status: str = Field(..., description="passed or failed")
    failures: list[QualityGateFailure] = Field(default_factory=list)
    execution_time_seconds: float = Field(..., ge=0.0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @property
    def passed(self) -> bool:
        """Whether all gates passed."""
        return self.status == "passed" and len(self.failures) == 0

    @property
    def has_critical_failures(self) -> bool:
        """Whether any failures are critical."""
        return any(f.severity == Severity.CRITICAL for f in self.failures)
```

---

## Entity Relationships

```
┌─────────────┐
│  projects   │
└──────┬──────┘
       │ 1
       │
       │ N
┌──────▼──────────┐
│     tasks       │  (enhanced with quality_gate_status, quality_gate_failures)
└──────┬──────────┘
       │ 1
       ├──────────────────┐
       │ N                │ N
┌──────▼──────────┐  ┌───▼──────────────┐
│  code_reviews   │  │  token_usage     │
└─────────────────┘  └──────────────────┘

┌─────────────┐
│  projects   │
└──────┬──────┘
       │ 1
       │
       │ N
┌──────▼──────────┐
│  checkpoints    │  (enhanced with name, description, metadata)
└─────────────────┘
```

**Key Relationships**:
- One task → Many code reviews (1:N)
- One task → Many token usage records (1:N, optional)
- One project → Many checkpoints (1:N)
- One project → Many token usage records (1:N)

---

## State Transitions

### Quality Gate Status Lifecycle

```
pending → running → passed ✅
                 └→ failed ❌ (creates blocker)
```

**States**:
- `pending`: Quality gates not yet run
- `running`: Quality gates currently executing
- `passed`: All gates passed, task can be marked complete
- `failed`: One or more gates failed, task blocked

**Triggers**:
- `pending → running`: Worker agent calls `complete_task()`
- `running → passed`: All quality checks pass
- `running → failed`: Any quality check fails with CRITICAL or HIGH severity

---

### Checkpoint Lifecycle

```
created → validated → (can be restored)
      └→ invalid ❌ (missing files)
```

**States**:
- `created`: Checkpoint metadata saved to database
- `validated`: Files exist and are readable
- `invalid`: Files missing or corrupted (checkpoint cannot be restored)

**Triggers**:
- `created`: User runs `codeframe checkpoint create <name>`
- `validated`: System verifies `database_backup_path` and `context_snapshot_path` exist
- `invalid`: File check fails during restore attempt

---

## Validation Rules

### CodeReview Validation
- `file_path` must be relative (no absolute paths)
- `line_number` must be positive if provided
- `message` minimum 10 characters
- `severity` must be valid enum value
- `category` must be valid enum value

### TokenUsage Validation
- `input_tokens` ≥ 0
- `output_tokens` ≥ 0
- `estimated_cost_usd` ≥ 0.0
- `actual_cost_usd` ≥ 0.0 if provided
- `model_name` must be known model (claude-sonnet-4-5, claude-opus-4, claude-haiku-4)

### Checkpoint Validation
- `name` 1-100 characters
- `description` ≤ 500 characters
- `git_commit` 7-40 characters (short or full SHA)
- `database_backup_path` must exist before marking valid
- `context_snapshot_path` must exist before marking valid

### QualityGateResult Validation
- `execution_time_seconds` ≥ 0.0
- `status` must be "passed" or "failed"
- `failures` must be empty if status is "passed"

---

## Indexes and Performance

### Critical Indexes
```sql
-- Fast lookup of reviews by task
CREATE INDEX idx_reviews_task ON code_reviews(task_id);

-- Fast filtering of critical findings
CREATE INDEX idx_reviews_severity ON code_reviews(severity, created_at);

-- Fast project-wide review reports
CREATE INDEX idx_reviews_project ON code_reviews(project_id, created_at);

-- Fast agent cost tracking
CREATE INDEX idx_token_usage_agent ON token_usage(agent_id, timestamp);

-- Fast project cost tracking
CREATE INDEX idx_token_usage_project ON token_usage(project_id, timestamp);

-- Fast checkpoint listing
CREATE INDEX idx_checkpoints_project ON checkpoints(project_id, created_at DESC);
```

**Query Optimization**:
- Use indexes for filtering (WHERE clauses)
- Use DESC for reverse chronological order (most recent first)
- Use composite indexes for multi-column queries (project_id + timestamp)

---

## Migration Strategy

### Step 1: Create new tables
```python
# In database.py, add to _create_schema()
cursor.execute("""CREATE TABLE code_reviews (...)""")
cursor.execute("""CREATE TABLE token_usage (...)""")
```

### Step 2: Alter existing tables
```python
# In database.py, add to _run_migrations() or create new migration file
cursor.execute("""ALTER TABLE tasks ADD COLUMN quality_gate_status TEXT""")
cursor.execute("""ALTER TABLE checkpoints ADD COLUMN name TEXT""")
```

### Step 3: Create indexes
```python
# After table creation
cursor.execute("""CREATE INDEX idx_reviews_task ON code_reviews(task_id)""")
cursor.execute("""CREATE INDEX idx_token_usage_agent ON token_usage(agent_id, timestamp)""")
cursor.execute("""CREATE INDEX idx_checkpoints_project ON checkpoints(project_id, created_at DESC)""")
```

### Step 4: Validate schema
```python
# Test migrations in test_database.py
def test_sprint10_schema():
    db = Database(":memory:")
    db.initialize()
    # Verify tables exist
    assert table_exists(db, "code_reviews")
    assert table_exists(db, "token_usage")
    # Verify columns exist
    assert column_exists(db, "tasks", "quality_gate_status")
    assert column_exists(db, "checkpoints", "name")
```

---

## Summary

**New Entities**: CodeReview, TokenUsage, Checkpoint (enhanced), QualityGateResult
**New Tables**: code_reviews, token_usage
**Modified Tables**: tasks (quality gates), checkpoints (metadata)
**New Indexes**: 6 indexes for performance
**Validation**: Pydantic models enforce data integrity
**Relationships**: Maintain referential integrity with foreign keys and ON DELETE CASCADE
