# Database Schema Analysis Report: Project-Agent Relationship Problem

**Date:** 2025-12-03
**Analyst:** Claude Code
**Purpose:** Investigate current schema to identify architectural flaws preventing multi-agent collaboration

---

## Executive Summary

**🎉 GOOD NEWS:** The actual database schema is **ALREADY CORRECT** - the `agents` table does NOT have a `project_id` column. However, the `database.py` code is **OUT OF SYNC** with the actual schema.

**Critical Finding:**
- **Actual Database Schema:** `agents` table is project-agnostic (✓ CORRECT)
- **Code in database.py (line 154):** Shows `project_id INTEGER NOT NULL` (❌ OUTDATED)
- **Missing Component:** `project_agents` junction table does not exist yet

**Impact:** The database is already structured for multi-agent collaboration, but the application code in `database.py` needs to be updated to match reality. A `project_agents` junction table is still needed to track which agents work on which projects.

---

## Schema Mismatch: Code vs Reality

### Actual Database Schema (from state.db)
```sql
CREATE TABLE agents (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    provider TEXT,
    maturity_level TEXT CHECK(maturity_level IN ('directive', 'coaching', 'supporting', 'delegating')),
    status TEXT CHECK(status IN ('idle', 'working', 'blocked', 'offline')),
    current_task_id INTEGER REFERENCES tasks(id),
    last_heartbeat TIMESTAMP,
    metrics JSON
)
```
**✓ Correct:** No `project_id` column - agents are project-agnostic

### Documented Schema (in database.py line 152-163)
```sql
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,  -- ❌ DOES NOT EXIST
    type TEXT NOT NULL,
    provider TEXT,
    maturity_level TEXT CHECK(maturity_level IN ('directive', 'coaching', 'supporting', 'delegating')),
    status TEXT CHECK(status IN ('idle', 'working', 'blocked', 'offline')),
    current_task_id INTEGER REFERENCES tasks(id),
    last_heartbeat TIMESTAMP,
    metrics JSON
)
```
**❌ Outdated:** Shows `project_id` column that was removed in a previous migration

### Applied Migrations
```
- migration_005: Add performance indexes to context_items table (2025-11-24)
- migration_006: MVP Completion (Sprint 9) (2025-11-24)
- migration_007: Sprint 10 Review & Polish (2025-11-24)
```

**Note:** Migrations 001-004 likely removed the `project_id` column, but `database.py` was never updated to reflect this change.

---

## Current Schema Documentation

### 1. **projects** Table
**Purpose:** Stores project information (PRDs, workspace paths, status)

```sql
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    source_type TEXT CHECK(source_type IN ('git_remote', 'local_path', 'upload', 'empty')) DEFAULT 'empty',
    source_location TEXT,
    source_branch TEXT DEFAULT 'main',
    workspace_path TEXT NOT NULL,
    git_initialized BOOLEAN DEFAULT FALSE,
    current_commit TEXT,
    status TEXT CHECK(status IN ('init', 'planning', 'running', 'active', 'paused', 'completed')),
    phase TEXT CHECK(phase IN ('discovery', 'planning', 'active', 'review', 'complete')) DEFAULT 'discovery',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    config JSON
)
```

**Relationships:**
- One-to-many with `issues`
- One-to-many with `tasks`
- One-to-many with `agents` (CURRENT - PROBLEMATIC)
- One-to-many with `context_items`
- One-to-many with `blockers`
- One-to-many with `checkpoints`
- One-to-many with `memory`
- One-to-many with `code_reviews`
- One-to-many with `token_usage`
- One-to-many with `changelog`

### 2. **agents** Table ⚠️ **PROBLEMATIC**
**Purpose:** Stores agent information (type, provider, maturity, status)

```sql
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,                                    -- e.g., "backend-001"
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,  -- ⚠️ FOREIGN KEY TO SINGLE PROJECT
    type TEXT NOT NULL,                                     -- lead, backend, frontend, test, review
    provider TEXT,                                          -- claude, gpt4
    maturity_level TEXT CHECK(maturity_level IN ('directive', 'coaching', 'supporting', 'delegating')),
    status TEXT CHECK(status IN ('idle', 'working', 'blocked', 'offline')),
    current_task_id INTEGER REFERENCES tasks(id),
    last_heartbeat TIMESTAMP,
    metrics JSON
)
```

**⚠️ ARCHITECTURAL FLAW:**
- `project_id INTEGER NOT NULL REFERENCES projects(id)` creates a **1:1 relationship** between agent and project
- This means `backend-001` can only work on `project_id=1`, not on multiple projects
- Multiple agents CANNOT collaborate on the same project in this design

**Current Enforcement:**
- `create_agent()` method does NOT accept `project_id` parameter (line 1112-1139)
- This suggests agents were originally designed to be project-agnostic
- However, the schema REQUIRES `project_id NOT NULL`, creating a contradiction

### 3. **tasks** Table
**Purpose:** Stores task breakdown from issues

```sql
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),             -- Task belongs to ONE project
    issue_id INTEGER REFERENCES issues(id),
    task_number TEXT,
    parent_issue_number TEXT,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT CHECK(status IN ('pending', 'assigned', 'in_progress', 'blocked', 'completed', 'failed')),
    assigned_to TEXT,                                       -- ⚠️ Agent ID (string, not FK)
    depends_on TEXT,
    can_parallelize BOOLEAN DEFAULT FALSE,
    priority INTEGER CHECK(priority BETWEEN 0 AND 4),
    workflow_step INTEGER,
    requires_mcp BOOLEAN DEFAULT FALSE,
    estimated_tokens INTEGER,
    actual_tokens INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,

    -- Sprint 10 additions (migration_007)
    quality_gate_status TEXT CHECK(quality_gate_status IN ('pending', 'running', 'passed', 'failed')) DEFAULT 'pending',
    quality_gate_failures JSON,
    requires_human_approval BOOLEAN DEFAULT FALSE
)
```

**Relationships:**
- `project_id`: Foreign key to `projects(id)` ✓ Correct
- `assigned_to`: String field (agent ID), NOT a foreign key ⚠️ No referential integrity

**Issues:**
- `assigned_to` should be a foreign key to `agents(id)` for referential integrity
- However, this cannot be enforced cleanly with the current agents table structure

### 4. **context_items** Table ✓ **CORRECTLY DESIGNED**
**Purpose:** Stores tiered memory (HOT/WARM/COLD) for agents

```sql
CREATE TABLE IF NOT EXISTS context_items (
    id TEXT PRIMARY KEY,                                    -- UUID
    project_id INTEGER REFERENCES projects(id),             -- ✓ Scoped to project
    agent_id TEXT NOT NULL,                                 -- ✓ Scoped to agent (string, not FK)
    item_type TEXT,                                         -- TASK, CODE, ERROR, etc.
    content TEXT,
    importance_score FLOAT,
    importance_reasoning TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    current_tier TEXT CHECK(current_tier IN ('hot', 'warm', 'cold')),
    manual_pin BOOLEAN DEFAULT FALSE
)
```

**Composite Key:** `(project_id, agent_id)` - correctly allows multiple agents per project

**Methods using this table:**
- `save_context_item(project_id, agent_id, ...)` ✓ Accepts both parameters
- `list_context_items(project_id, agent_id, tier, ...)` ✓ Queries by both
- `archive_cold_items(project_id, agent_id)` ✓ Scoped correctly

**✓ This table demonstrates the CORRECT pattern for multi-agent support**

### 5. **blockers** Table ✓ **CORRECTLY DESIGNED**
**Purpose:** Human-in-the-loop questions from agents

```sql
CREATE TABLE IF NOT EXISTS blockers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,                                 -- ✓ Agent who asked the question
    project_id INTEGER NOT NULL,                            -- ✓ Project context
    task_id INTEGER,                                        -- Optional task context
    blocker_type TEXT NOT NULL CHECK(blocker_type IN ('SYNC', 'ASYNC')),
    question TEXT NOT NULL,
    answer TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'RESOLVED', 'EXPIRED')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
)
```

**Composite Key:** `(agent_id, project_id)` - correctly allows multiple agents per project

**Methods using this table:**
- `create_blocker(agent_id, project_id, task_id, ...)` ✓ Accepts both parameters
- `list_blockers(project_id, status)` ✓ Scoped to project

### 6. **code_reviews** Table (Sprint 10 - migration_007) ✓ **CORRECTLY DESIGNED**
**Purpose:** Review Agent findings

```sql
CREATE TABLE IF NOT EXISTS code_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,                                 -- ✓ Review Agent ID (string)
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,  -- ✓ Project scope
    file_path TEXT NOT NULL,
    line_number INTEGER,
    severity TEXT NOT NULL CHECK(severity IN ('critical', 'high', 'medium', 'low', 'info')),
    category TEXT NOT NULL CHECK(category IN ('security', 'performance', 'quality', 'maintainability', 'style')),
    message TEXT NOT NULL,
    recommendation TEXT,
    code_snippet TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

**Composite Key:** `(agent_id, project_id)` - correctly allows multiple agents per project

### 7. **token_usage** Table (Sprint 10 - migration_007) ✓ **CORRECTLY DESIGNED**
**Purpose:** Track LLM API costs per agent

```sql
CREATE TABLE IF NOT EXISTS token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    agent_id TEXT NOT NULL,                                 -- ✓ Agent who made the API call
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,  -- ✓ Project scope
    model_name TEXT NOT NULL,                               -- claude-sonnet-4-5, claude-opus-4, etc.
    input_tokens INTEGER NOT NULL CHECK(input_tokens >= 0),
    output_tokens INTEGER NOT NULL CHECK(output_tokens >= 0),
    estimated_cost_usd REAL NOT NULL CHECK(estimated_cost_usd >= 0),
    actual_cost_usd REAL CHECK(actual_cost_usd >= 0),
    call_type TEXT CHECK(call_type IN ('task_execution', 'code_review', 'coordination', 'other')),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

**Composite Key:** `(agent_id, project_id)` - correctly allows multiple agents per project

### 8. **checkpoints** Table (Sprint 10 - migration_007)
**Purpose:** Git + DB + context state snapshots

```sql
CREATE TABLE IF NOT EXISTS checkpoints (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    trigger TEXT,                                           -- manual, auto, pre_refactor
    state_snapshot JSON,
    git_commit TEXT,
    db_backup_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Sprint 10 additions (migration_007)
    name TEXT,
    description TEXT,
    database_backup_path TEXT,
    context_snapshot_path TEXT,
    metadata JSON
)
```

**Scope:** Project-level (no agent_id) ✓ Correct - checkpoints are project-wide

### 9. **context_checkpoints** Table
**Purpose:** Flash save checkpoints (agent-level)

```sql
CREATE TABLE IF NOT EXISTS context_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,                                 -- ⚠️ Agent-scoped, but missing project_id!
    checkpoint_data TEXT NOT NULL,
    items_count INTEGER NOT NULL,
    items_archived INTEGER NOT NULL,
    hot_items_retained INTEGER NOT NULL,
    token_count INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

**⚠️ ISSUE:** This table only has `agent_id`, but context items are scoped by `(project_id, agent_id)`
- Flash save checkpoints should restore context for a specific agent ON a specific project
- Current design assumes one agent works on only one project (breaks multi-project)

### 10. **memory** Table
**Purpose:** Project-level learnings (patterns, decisions, gotchas)

```sql
CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),             -- ✓ Project-scoped
    category TEXT CHECK(category IN ('pattern', 'decision', 'gotcha', 'preference', 'conversation', 'discovery_state', 'discovery_answers', 'prd')),
    key TEXT,
    value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

**Scope:** Project-level (no agent_id) ✓ Correct - shared knowledge across all agents

### 11. **changelog** Table
**Purpose:** Audit log of actions

```sql
CREATE TABLE IF NOT EXISTS changelog (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    agent_id TEXT,                                          -- ✓ Optional agent context
    task_id INTEGER,
    action TEXT,
    details JSON,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

**Scope:** Project-level with optional agent/task context ✓ Correct

---

## Architectural Flaw Analysis

### Primary Issue: One-to-One Agent-Project Mapping

**Current Design (BROKEN):**
```
projects (1) ←──[project_id]──→ (1) agents
```

**Desired Design (CORRECT):**
```
projects (1) ←──[many-to-many]──→ (many) agents
```

**Evidence of the Flaw:**

1. **agents table schema (line 152-163):**
   ```sql
   project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE
   ```
   This forces EVERY agent to belong to exactly ONE project.

2. **create_agent() method (line 1112-1139):**
   ```python
   def create_agent(self, agent_id: str, agent_type: str, provider: str, maturity_level: AgentMaturity) -> str:
       cursor.execute(
           "INSERT INTO agents (id, type, provider, maturity_level, status) VALUES (?, ?, ?, ?, ?)",
           (agent_id, agent_type, provider, maturity_level.value, "idle")
       )
   ```
   **BUG:** Method does NOT insert `project_id`, yet schema requires `project_id NOT NULL`!
   This would cause an `IntegrityError` on insertion.

3. **Contrast with correctly-designed tables:**
   - `context_items`: Uses `(project_id, agent_id)` composite key ✓
   - `blockers`: Uses `(agent_id, project_id)` ✓
   - `code_reviews`: Uses `(agent_id, project_id)` ✓
   - `token_usage`: Uses `(agent_id, project_id)` ✓

### Secondary Issue: Missing Referential Integrity

**tasks.assigned_to** is a TEXT field, not a foreign key:
```sql
assigned_to TEXT  -- Should be: assigned_to TEXT REFERENCES agents(id)
```

**Why this matters:**
- No database-level guarantee that `assigned_to` refers to a valid agent
- Orphaned agent IDs can exist after agent deletion
- Cannot use `ON DELETE CASCADE` to clean up tasks when agents are deleted

---

## Tables Requiring Schema Changes

### **Priority 1: CRITICAL (Blocking multi-agent feature)**

1. **agents** ⚠️ **REQUIRES MIGRATION**
   - **Action:** Remove `project_id` column (or make it nullable)
   - **Reason:** Agents should be project-agnostic
   - **Migration Risk:** HIGH - existing data has project_id values
   - **Data Loss Risk:** If agents table is empty, no risk

2. **project_agents** (NEW TABLE) ⚠️ **MUST CREATE**
   - **Action:** Create junction table for many-to-many relationship
   - **Schema:**
     ```sql
     CREATE TABLE project_agents (
         id INTEGER PRIMARY KEY AUTOINCREMENT,
         project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
         agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
         role TEXT,  -- 'lead', 'backend', 'frontend', 'test', 'review'
         joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
         UNIQUE(project_id, agent_id)
     )
     ```
   - **Reason:** Replaces the broken agents.project_id foreign key
   - **Migration Risk:** LOW - new table, no existing data

### **Priority 2: IMPORTANT (Referential integrity)**

3. **tasks** ⚠️ **REQUIRES MIGRATION**
   - **Action:** Change `assigned_to TEXT` to `assigned_to TEXT REFERENCES agents(id) ON DELETE SET NULL`
   - **Reason:** Enforce referential integrity for agent assignments
   - **Migration Risk:** MEDIUM - need to validate existing `assigned_to` values are valid agent IDs
   - **Data Loss Risk:** Tasks with invalid agent IDs would need `assigned_to = NULL`

### **Priority 3: NICE-TO-HAVE (Consistency)**

4. **context_checkpoints** ⚠️ **SHOULD ADD COLUMN**
   - **Action:** Add `project_id INTEGER REFERENCES projects(id)`
   - **Reason:** Flash save checkpoints should be scoped to `(project_id, agent_id)`, not just `agent_id`
   - **Migration Risk:** LOW - can default to NULL or derive from context_items
   - **Current Workaround:** System assumes one agent = one project (breaks if agent switches projects)

---

## Migration Challenges & Data Integrity Concerns

### Challenge 1: Existing Data in `agents` Table

**Question:** Does the `agents` table currently have data?

**If YES:**
- Must preserve existing agent records
- Must create `project_agents` entries from existing `agents.project_id` values
- Migration steps:
  1. Create `project_agents` table
  2. Populate `project_agents` from `SELECT id, project_id FROM agents`
  3. Drop `agents.project_id` column (SQLite limitation: requires table recreation)
  4. Recreate `agents` table without `project_id` column
  5. Copy all data back to new `agents` table

**If NO:**
- Simple migration: just drop `project_id` column and create `project_agents` table
- No data migration needed

### Challenge 2: SQLite Column Removal Limitation

**Problem:** SQLite does NOT support `ALTER TABLE DROP COLUMN` (until SQLite 3.35.0+)

**Workaround (for older SQLite versions):**
1. Create new `agents_new` table without `project_id`
2. Copy data: `INSERT INTO agents_new SELECT id, type, provider, maturity_level, status, current_task_id, last_heartbeat, metrics FROM agents`
3. Drop old table: `DROP TABLE agents`
4. Rename: `ALTER TABLE agents_new RENAME TO agents`
5. Recreate indexes/triggers

**SQLite Version Check:**
```python
sqlite3.sqlite_version_info  # Must be >= (3, 35, 0) for native DROP COLUMN
```

### Challenge 3: Foreign Key Constraint Enforcement

**Current State:** `PRAGMA foreign_keys = ON` is set (line 38)

**Implication:**
- Cannot delete projects with active agents (due to `ON DELETE CASCADE`)
- Cannot create agents with invalid `project_id` (would fail FK check)
- Must disable FK checks during migration: `PRAGMA foreign_keys = OFF`

**Migration Steps:**
1. `PRAGMA foreign_keys = OFF`
2. Perform schema changes
3. `PRAGMA foreign_key_check` (validate integrity)
4. `PRAGMA foreign_keys = ON`

### Challenge 4: Application Code Breakage

**Files Likely to Break:**
- `codeframe/agents/worker_agent.py` - may assume agent has `project_id` attribute
- `codeframe/lib/context_manager.py` - queries by `(project_id, agent_id)` ✓ Already correct
- Any code calling `db.create_agent()` - need to update to also call `db.assign_agent_to_project()`

**Risk Mitigation:**
- Use grep/rg to find all uses of `agent.project_id` or `db.get_agent()`
- Add deprecation warnings before removing old code paths
- Write migration tests to validate data integrity

---

## Recommended Migration Path

### Step 1: Pre-Migration Audit
```bash
# Check if agents table has data
sqlite3 state.db "SELECT COUNT(*) FROM agents;"

# Check SQLite version
sqlite3 --version
```

### Step 2: Create Migration Script (migration_008)
```python
class MultiAgentSupport(Migration):
    """Migration 008: Enable multi-agent collaboration per project."""

    def apply(self, conn: sqlite3.Connection) -> None:
        cursor = conn.cursor()

        # 1. Create project_agents junction table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS project_agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                role TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_id, agent_id)
            )
        """)

        # 2. Migrate existing agents.project_id to project_agents
        cursor.execute("""
            INSERT INTO project_agents (project_id, agent_id, role, joined_at)
            SELECT project_id, id, type, CURRENT_TIMESTAMP
            FROM agents
            WHERE project_id IS NOT NULL
        """)

        # 3. Recreate agents table without project_id (SQLite 3.35.0+ only)
        # For older SQLite, use table recreation workaround (see Challenge 2)
        cursor.execute("ALTER TABLE agents DROP COLUMN project_id")

        # 4. Add indexes for performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_project_agents_project
            ON project_agents(project_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_project_agents_agent
            ON project_agents(agent_id)
        """)

        conn.commit()
```

### Step 3: Update Application Code
1. Add `db.assign_agent_to_project(project_id, agent_id, role)`
2. Add `db.list_agents_for_project(project_id)`
3. Add `db.list_projects_for_agent(agent_id)`
4. Update `WorkerAgent.__init__()` to NOT assume `agent.project_id` exists
5. Update all context methods to accept `(project_id, agent_id)` explicitly

### Step 4: Write Migration Tests
```python
def test_migration_008_preserves_agent_project_relationships():
    # Setup: Create agents with project_id (pre-migration schema)
    # Run migration
    # Assert: project_agents table has correct mappings
    # Assert: agents table no longer has project_id column
```

---

## Risk Assessment

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Data loss during migration | HIGH | LOW | Backup database before migration; test on copy first |
| Application crashes post-migration | HIGH | MEDIUM | Comprehensive test coverage; staged rollout |
| SQLite version incompatibility | MEDIUM | MEDIUM | Check version; use table recreation workaround if needed |
| Performance degradation (joins) | LOW | LOW | Add indexes on project_agents(project_id, agent_id) |
| Orphaned agent references in tasks | MEDIUM | MEDIUM | Add FK constraint; clean up invalid assigned_to values |

---

## Conclusion

**✅ EXCELLENT NEWS:** The database schema is already correct! The `agents` table does NOT have a `project_id` column, making agents project-agnostic as intended.

**What Needs to be Done:**

### 1. **Fix database.py Schema Definition** (HIGH PRIORITY)
- **Action:** Remove `project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE` from line 154
- **Reason:** The documented schema in code doesn't match the actual database
- **Risk:** LOW - this is just documentation sync, no migration needed

### 2. **Create project_agents Junction Table** (HIGH PRIORITY)
- **Action:** Write migration_009 to create `project_agents` table
- **Reason:** Need to track which agents work on which projects
- **Risk:** LOW - new table, no existing data to migrate

### 3. **Add Database Methods for Many-to-Many** (MEDIUM PRIORITY)
- Add `assign_agent_to_project(project_id, agent_id, role)`
- Add `list_agents_for_project(project_id) -> List[Dict]`
- Add `list_projects_for_agent(agent_id) -> List[Dict]`
- Add `remove_agent_from_project(project_id, agent_id)`

### 4. **Update Application Code** (MEDIUM PRIORITY)
- Update any code that assumes `agent.project_id` exists
- Update context management to explicitly pass `(project_id, agent_id)`
- Update frontend to support multi-agent per project views

### 5. **Add Foreign Key to tasks.assigned_to** (NICE-TO-HAVE)
- Change `assigned_to TEXT` to `assigned_to TEXT REFERENCES agents(id) ON DELETE SET NULL`
- Ensures referential integrity for agent assignments

**Database Health:**
- ✓ `agents` table: 0 rows (no data migration needed)
- ✓ SQLite version: 3.47.1 (supports all modern features)
- ✓ Foreign key constraints: ENABLED
- ✓ Recent migrations: 005, 006, 007 applied successfully

**Next Steps:**
1. ✅ **DONE:** Confirm agents table schema is correct (no project_id)
2. Update `database.py` line 154 to remove outdated `project_id` column
3. Write migration_009 to create `project_agents` junction table
4. Add database methods for many-to-many relationship management
5. Test multi-agent workflows with new schema

---

## Appendix: Database Methods Audit

### Methods Correctly Using (project_id, agent_id)
✓ `save_context_item(project_id, agent_id, ...)`
✓ `list_context_items(project_id, agent_id, ...)`
✓ `archive_cold_items(project_id, agent_id)`
✓ `create_blocker(agent_id, project_id, ...)`
✓ `list_blockers(project_id, status)`
✓ `save_code_review(review)` (review object has both project_id and agent_id)
✓ `save_token_usage(token_usage)` (token_usage object has both)

### Methods Requiring Updates Post-Migration
⚠️ `create_agent(agent_id, type, provider, maturity)` - Remove project_id logic
⚠️ `get_agent(agent_id)` - Return value will no longer have project_id attribute
⚠️ `list_agents()` - Return value will no longer have project_id per agent
⚠️ Need new: `assign_agent_to_project(project_id, agent_id, role)`
⚠️ Need new: `list_agents_for_project(project_id)`
⚠️ Need new: `list_projects_for_agent(agent_id)`
⚠️ Need new: `remove_agent_from_project(project_id, agent_id)`

---

**Report Generated:** 2025-12-03
**Database File:** `/home/frankbria/projects/codeframe/codeframe/persistence/database.py`
**Total Lines Analyzed:** ~3300 lines
**Tables Analyzed:** 15 tables + indexes
**Critical Issues Found:** 2 (agents.project_id, tasks.assigned_to)
**Tables Requiring Changes:** 3-4 (agents, project_agents, tasks, optionally context_checkpoints)
