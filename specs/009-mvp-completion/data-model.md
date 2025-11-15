# Data Model: Sprint 9 MVP Completion

**Date**: 2025-11-15
**Branch**: 009-mvp-completion
**Migration**: migration_006_mvp_completion.py

## Overview

This document specifies all database schema changes and entity models for Sprint 9. Changes include: new `lint_results` table, `commit_sha` column in tasks, composite index on `context_items`, and potential `review_results` table (if needed).

---

## Schema Changes

### 1. New Table: `lint_results`

Stores lint execution results for tracking quality trends over time.

```sql
CREATE TABLE lint_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    linter TEXT NOT NULL CHECK(linter IN ('ruff', 'eslint', 'other')),
    error_count INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    files_linted INTEGER NOT NULL DEFAULT 0,
    output TEXT,  -- Full lint output (JSON or text)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);
```

**Index**:
```sql
CREATE INDEX idx_lint_results_task ON lint_results(task_id);
CREATE INDEX idx_lint_results_created ON lint_results(created_at DESC);
```

**Purpose**:
- Track lint quality over time (trend analysis)
- Store detailed lint output for debugging
- Support dashboard visualization (lint errors chart)
- Audit trail for quality enforcement

**Columns**:
- `task_id`: Links lint results to task execution
- `linter`: Tool used (ruff, eslint, or extensible "other")
- `error_count`: Critical errors that block task completion
- `warning_count`: Non-blocking warnings
- `files_linted`: Number of files checked (for coverage tracking)
- `output`: Full lint output (JSON for ruff/eslint, text fallback)
- `created_at`: Timestamp for trend analysis

**Usage Example**:
```python
# Store lint results after execution
cursor.execute("""
    INSERT INTO lint_results (task_id, linter, error_count, warning_count, files_linted, output)
    VALUES (?, ?, ?, ?, ?, ?)
""", (task_id, 'ruff', 3, 12, 45, json.dumps(lint_output)))
```

---

### 2. Modified Table: `tasks`

Add `commit_sha` column to track git commits created after task completion.

```sql
ALTER TABLE tasks ADD COLUMN commit_sha TEXT;
```

**Index** (optional, for commit lookups):
```sql
CREATE INDEX idx_tasks_commit_sha ON tasks(commit_sha) WHERE commit_sha IS NOT NULL;
```

**Purpose**:
- Link tasks to git commits for traceability
- Enable git bisect for debugging (find task that introduced regression)
- Support changelog generation
- Audit trail for version control continuity

**Column Details**:
- `commit_sha`: Full git commit hash (40 chars, nullable)
- Nullable: Old tasks won't have commits (backward compatible)
- Updated after successful commit in worker agent

**Usage Example**:
```python
# Update task with commit SHA after auto-commit
commit_sha = git_workflow.commit_task_changes(task, files_modified, agent_id)

cursor.execute("""
    UPDATE tasks SET commit_sha = ? WHERE id = ?
""", (commit_sha, task_id))
```

---

### 3. New Index: `context_items`

Create composite index for performance optimization on context queries.

```sql
CREATE INDEX idx_context_project_agent
ON context_items(project_id, agent_id, current_tier);
```

**Purpose**:
- Optimize most common query: "Get HOT context for agent X on project Y"
- Reduce query time from O(n) to O(log n)
- Enable index-only scans (all filter columns in index)
- Improve dashboard responsiveness

**Query Pattern**:
```sql
-- This query will now use the new index
SELECT * FROM context_items
WHERE project_id = ? AND agent_id = ? AND current_tier = 'hot'
ORDER BY last_accessed DESC;
```

**Performance Impact**:
- **Before**: Full table scan with agent_id filter
- **After**: Index seek with (project_id, agent_id, current_tier)
- **Expected Improvement**: 50-90% reduction in query time

---

### 4. Optional Table: `review_results` (TBD)

If review results need separate storage from `lint_results`, create dedicated table.

**Decision**: Start without separate table, use lint_results + blocker system

**Rationale**:
- Review findings stored as blockers (existing mechanism)
- Lint results table covers quality metrics
- Avoid premature abstraction

**Future Consideration** (v2):
If review results become too complex for blockers, create:
```sql
CREATE TABLE review_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    reviewer_agent_id TEXT NOT NULL REFERENCES agents(id),
    complexity_score REAL,  -- 0.0-100.0
    security_score REAL,    -- 0.0-100.0
    style_score REAL,       -- 0.0-100.0
    overall_score REAL,     -- Weighted average
    status TEXT CHECK(status IN ('approved', 'changes_requested', 'rejected')),
    findings JSON,          -- Detailed findings
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);
```

**For MVP**: Use blockers + lint_results (simpler, less overhead)

---

## Entity Models

### LintResult (Pydantic Model)

```python
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime

class LintResult(BaseModel):
    """Lint execution result."""

    id: Optional[int] = None
    task_id: int = Field(..., description="Task ID")
    linter: Literal['ruff', 'eslint', 'other'] = Field(..., description="Linter tool")
    error_count: int = Field(0, ge=0, description="Number of errors")
    warning_count: int = Field(0, ge=0, description="Number of warnings")
    files_linted: int = Field(0, ge=0, description="Number of files checked")
    output: Optional[str] = Field(None, description="Full lint output (JSON or text)")
    created_at: Optional[datetime] = None

    @property
    def has_critical_errors(self) -> bool:
        """Check if lint found critical errors that block task."""
        return self.error_count > 0

    @property
    def total_issues(self) -> int:
        """Total issues (errors + warnings)."""
        return self.error_count + self.warning_count

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        return {
            'task_id': self.task_id,
            'linter': self.linter,
            'error_count': self.error_count,
            'warning_count': self.warning_count,
            'files_linted': self.files_linted,
            'output': self.output,
        }
```

---

### ReviewFinding (Pydantic Model)

Used for Review Agent findings (stored in blocker details).

```python
from pydantic import BaseModel, Field
from typing import Literal

class ReviewFinding(BaseModel):
    """Individual review finding."""

    category: Literal['complexity', 'security', 'style', 'duplication'] = Field(
        ..., description="Finding category"
    )
    severity: Literal['critical', 'high', 'medium', 'low'] = Field(
        ..., description="Severity level"
    )
    file_path: str = Field(..., description="File with issue")
    line_number: Optional[int] = Field(None, description="Line number (if applicable)")
    message: str = Field(..., description="Human-readable description")
    suggestion: Optional[str] = Field(None, description="Recommended fix")
    tool: str = Field(..., description="Tool that detected issue (radon, bandit, etc.)")

    def to_markdown(self) -> str:
        """Format finding as markdown for blocker display."""
        severity_emoji = {
            'critical': '🔴',
            'high': '🟠',
            'medium': '🟡',
            'low': '⚪'
        }

        location = f"{self.file_path}:{self.line_number}" if self.line_number else self.file_path

        md = f"{severity_emoji[self.severity]} **{self.severity.upper()}** [{self.category}] {location}\n"
        md += f"   {self.message}\n"

        if self.suggestion:
            md += f"   💡 Suggestion: {self.suggestion}\n"

        return md


class ReviewReport(BaseModel):
    """Complete review report for a task."""

    task_id: int
    reviewer_agent_id: str
    overall_score: float = Field(..., ge=0, le=100, description="Overall quality score (0-100)")
    complexity_score: float = Field(..., ge=0, le=100)
    security_score: float = Field(..., ge=0, le=100)
    style_score: float = Field(..., ge=0, le=100)
    status: Literal['approved', 'changes_requested', 'rejected']
    findings: list[ReviewFinding] = Field(default_factory=list)
    summary: str = Field(..., description="Human-readable summary")

    @property
    def has_critical_findings(self) -> bool:
        """Check if any findings are critical severity."""
        return any(f.severity == 'critical' for f in self.findings)

    @property
    def critical_count(self) -> int:
        """Count critical findings."""
        return sum(1 for f in self.findings if f.severity == 'critical')

    @property
    def high_count(self) -> int:
        """Count high severity findings."""
        return sum(1 for f in self.findings if f.severity == 'high')

    def to_blocker_message(self) -> str:
        """Format review report as blocker message."""
        msg = f"## Code Review: {self.status.replace('_', ' ').title()}\n\n"
        msg += f"**Overall Score**: {self.overall_score:.1f}/100\n\n"

        if self.findings:
            msg += f"**Findings**: {len(self.findings)} issues ({self.critical_count} critical, {self.high_count} high)\n\n"

            # Group by severity
            for severity in ['critical', 'high', 'medium', 'low']:
                severity_findings = [f for f in self.findings if f.severity == severity]
                if severity_findings:
                    msg += f"### {severity.upper()} Issues\n\n"
                    for finding in severity_findings:
                        msg += finding.to_markdown() + "\n"

        msg += f"\n---\n\n{self.summary}"

        return msg
```

---

## Database Methods

### LintResults

Add to `Database` class in `codeframe/persistence/database.py`:

```python
def create_lint_result(
    self,
    task_id: int,
    linter: str,
    error_count: int,
    warning_count: int,
    files_linted: int,
    output: str
) -> int:
    """Store lint execution result.

    Args:
        task_id: Task ID
        linter: Linter tool name ('ruff', 'eslint', 'other')
        error_count: Number of errors
        warning_count: Number of warnings
        files_linted: Number of files checked
        output: Full lint output (JSON or text)

    Returns:
        Lint result ID
    """
    cursor = self.conn.cursor()
    cursor.execute(
        """
        INSERT INTO lint_results (task_id, linter, error_count, warning_count, files_linted, output)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (task_id, linter, error_count, warning_count, files_linted, output)
    )
    self.conn.commit()
    return cursor.lastrowid


def get_lint_results_for_task(self, task_id: int) -> list[dict]:
    """Get all lint results for a task.

    Args:
        task_id: Task ID

    Returns:
        List of lint result dictionaries
    """
    cursor = self.conn.cursor()
    cursor.execute(
        """
        SELECT id, task_id, linter, error_count, warning_count, files_linted, output, created_at
        FROM lint_results
        WHERE task_id = ?
        ORDER BY created_at DESC
        """,
        (task_id,)
    )
    return [dict(row) for row in cursor.fetchall()]


def get_lint_trend(self, project_id: int, days: int = 7) -> list[dict]:
    """Get lint error trend for project over time.

    Args:
        project_id: Project ID
        days: Number of days to look back

    Returns:
        List of {date, linter, error_count, warning_count} dictionaries
    """
    cursor = self.conn.cursor()
    cursor.execute(
        """
        SELECT
            DATE(lr.created_at) as date,
            lr.linter,
            SUM(lr.error_count) as error_count,
            SUM(lr.warning_count) as warning_count
        FROM lint_results lr
        JOIN tasks t ON lr.task_id = t.id
        WHERE t.project_id = ?
          AND lr.created_at >= datetime('now', '-' || ? || ' days')
        GROUP BY DATE(lr.created_at), lr.linter
        ORDER BY date DESC
        """,
        (project_id, days)
    )
    return [dict(row) for row in cursor.fetchall()]
```

### Task Commit SHA

Update existing methods in `Database` class:

```python
def update_task_commit_sha(self, task_id: int, commit_sha: str) -> None:
    """Update task with git commit SHA.

    Args:
        task_id: Task ID
        commit_sha: Git commit hash
    """
    cursor = self.conn.cursor()
    cursor.execute(
        """
        UPDATE tasks SET commit_sha = ? WHERE id = ?
        """,
        (commit_sha, task_id)
    )
    self.conn.commit()


def get_task_by_commit(self, commit_sha: str) -> Optional[dict]:
    """Find task by git commit SHA.

    Args:
        commit_sha: Git commit hash (full or short)

    Returns:
        Task dictionary or None if not found
    """
    cursor = self.conn.cursor()
    # Support both full (40 char) and short (7 char) hashes
    cursor.execute(
        """
        SELECT * FROM tasks
        WHERE commit_sha = ? OR commit_sha LIKE ?
        LIMIT 1
        """,
        (commit_sha, f"{commit_sha}%")
    )
    row = cursor.fetchone()
    return dict(row) if row else None
```

---

## Migration Plan

### migration_006_mvp_completion.py

**File**: `/home/frankbria/projects/codeframe/codeframe/persistence/migrations/migration_006_mvp_completion.py`

```python
"""
Migration 006: MVP Completion (Sprint 9)

Changes:
1. Add commit_sha column to tasks table
2. Create lint_results table
3. Create composite index on context_items(project_id, agent_id, current_tier)

Date: 2025-11-15
Sprint: 009-mvp-completion
"""

import sqlite3
import logging

logger = logging.getLogger(__name__)


def upgrade(conn: sqlite3.Connection) -> None:
    """Apply migration 006."""
    cursor = conn.cursor()

    logger.info("Migration 006: Adding commit_sha to tasks table")
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN commit_sha TEXT")
        logger.info("✓ Added commit_sha column")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            logger.info("⊘ Column commit_sha already exists, skipping")
        else:
            raise

    logger.info("Migration 006: Creating lint_results table")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lint_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            linter TEXT NOT NULL CHECK(linter IN ('ruff', 'eslint', 'other')),
            error_count INTEGER NOT NULL DEFAULT 0,
            warning_count INTEGER NOT NULL DEFAULT 0,
            files_linted INTEGER NOT NULL DEFAULT 0,
            output TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        )
    """)
    logger.info("✓ Created lint_results table")

    logger.info("Migration 006: Creating indexes on lint_results")
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_lint_results_task
        ON lint_results(task_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_lint_results_created
        ON lint_results(created_at DESC)
    """)
    logger.info("✓ Created lint_results indexes")

    logger.info("Migration 006: Creating composite index on context_items")
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_context_project_agent
        ON context_items(project_id, agent_id, current_tier)
    """)
    logger.info("✓ Created composite index idx_context_project_agent")

    logger.info("Migration 006: Creating partial index on tasks.commit_sha")
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tasks_commit_sha
        ON tasks(commit_sha)
        WHERE commit_sha IS NOT NULL
    """)
    logger.info("✓ Created partial index on tasks.commit_sha")

    conn.commit()
    logger.info("Migration 006 completed successfully")


def downgrade(conn: sqlite3.Connection) -> None:
    """Rollback migration 006."""
    cursor = conn.cursor()

    logger.info("Migration 006: Rolling back changes")

    # Drop indexes
    cursor.execute("DROP INDEX IF EXISTS idx_context_project_agent")
    cursor.execute("DROP INDEX IF EXISTS idx_lint_results_task")
    cursor.execute("DROP INDEX IF EXISTS idx_lint_results_created")
    cursor.execute("DROP INDEX IF EXISTS idx_tasks_commit_sha")
    logger.info("✓ Dropped indexes")

    # Drop lint_results table
    cursor.execute("DROP TABLE IF EXISTS lint_results")
    logger.info("✓ Dropped lint_results table")

    # Cannot drop column in SQLite (requires table recreation)
    logger.warning(
        "⚠ Cannot drop commit_sha column from tasks table (SQLite limitation). "
        "Column will remain but be unused."
    )

    conn.commit()
    logger.info("Migration 006 rollback completed")
```

---

## ERD (Entity Relationship Diagram)

```
┌─────────────────┐
│    projects     │
└────────┬────────┘
         │
         │ 1:N
         │
┌────────▼────────┐         ┌──────────────────┐
│     tasks       │◄────────┤  lint_results    │
│                 │   1:N   │                  │
│ + commit_sha    │         │ + task_id (FK)   │
└────────┬────────┘         │ + linter         │
         │                  │ + error_count    │
         │                  │ + warning_count  │
         │                  └──────────────────┘
         │
         │ N:1
         │
┌────────▼────────┐
│  git commits    │  (external, linked via commit_sha)
└─────────────────┘

┌──────────────────┐
│  context_items   │
│                  │
│ [idx_context_    │  ← NEW COMPOSITE INDEX
│  project_agent]  │     (project_id, agent_id, current_tier)
└──────────────────┘
```

---

## Testing Requirements

### Database Tests

1. **Migration Tests** (5 tests):
   - `test_migration_006_upgrade()` - Apply migration successfully
   - `test_migration_006_idempotent()` - Re-running migration is safe
   - `test_migration_006_downgrade()` - Rollback works (except commit_sha)
   - `test_commit_sha_nullable()` - Old tasks don't break
   - `test_composite_index_exists()` - Index created and usable

2. **Lint Results Tests** (6 tests):
   - `test_create_lint_result()` - Insert lint result
   - `test_get_lint_results_for_task()` - Retrieve by task
   - `test_get_lint_trend()` - Aggregate over time
   - `test_lint_result_cascade_delete()` - Delete when task deleted
   - `test_lint_result_validation()` - Check constraints enforced
   - `test_multiple_linters_per_task()` - ruff + eslint both stored

3. **Commit SHA Tests** (4 tests):
   - `test_update_task_commit_sha()` - Update task with SHA
   - `test_get_task_by_commit()` - Lookup by full hash
   - `test_get_task_by_short_commit()` - Lookup by short hash (7 chars)
   - `test_commit_sha_index_used()` - Index used for lookups

4. **Index Performance Tests** (2 tests):
   - `test_composite_index_query_plan()` - EXPLAIN shows index used
   - `test_composite_index_performance()` - Benchmark query speed improvement

---

## API Impact

### New Endpoints

**GET /api/lint/results?task_id=123**
- Get lint results for specific task
- Response: List of LintResult objects

**GET /api/lint/trend?project_id=123&days=7**
- Get lint error trend over time
- Response: List of {date, linter, error_count, warning_count}

**GET /api/tasks/by-commit?sha=abc123**
- Find task by git commit SHA
- Response: Task object or 404

### Modified Endpoints

**GET /api/tasks/{task_id}**
- Add `commit_sha` field to response
- Nullable (old tasks won't have it)

**GET /api/agents/{agent_id}/context/items**
- No API change, but faster due to composite index
- Performance improvement transparent to clients

---

## Summary

**New Entities**:
- `lint_results` table (6 columns, 2 indexes)
- `LintResult` Pydantic model
- `ReviewFinding` Pydantic model
- `ReviewReport` Pydantic model

**Modified Entities**:
- `tasks` table: + `commit_sha` column
- `context_items`: + composite index

**Database Methods Added** (6):
- `create_lint_result()`
- `get_lint_results_for_task()`
- `get_lint_trend()`
- `update_task_commit_sha()`
- `get_task_by_commit()`

**Migration**:
- `migration_006_mvp_completion.py`
- 5 DDL statements (1 ALTER, 1 CREATE TABLE, 4 CREATE INDEX)
- Rollback supported (except column drop limitation)

**Testing**:
- 17 database tests
- 3 new API endpoints
- 1 modified API endpoint
