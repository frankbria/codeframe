# Multi-Agent Per Project Schema Design

## Executive Summary

This document defines the database schema design for multi-agent per project architecture. The key insight is that agents are **reusable resources** that can work on multiple projects, requiring a many-to-many relationship via a junction table.

**Core Design Principle**: One agent (e.g., `backend-001`) can work on multiple projects simultaneously or sequentially, and one project can have multiple agents working on it.

---

## 1. Schema Design

### 1.1 Updated `agents` Table

**Current schema (line 152-163 in database.py) is INCORRECT** - it includes `project_id` which violates the reusable agent principle.

**Correct Schema**:
```sql
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,                    -- e.g., "backend-001", "frontend-002"
    type TEXT NOT NULL,                     -- e.g., "lead", "backend", "frontend", "test", "review"
    provider TEXT,                          -- e.g., "claude", "gpt4"
    maturity_level TEXT CHECK(maturity_level IN ('directive', 'coaching', 'supporting', 'delegating')),
    status TEXT CHECK(status IN ('idle', 'working', 'blocked', 'offline')),
    current_task_id INTEGER REFERENCES tasks(id),  -- Current task being worked on (NULL if idle)
    last_heartbeat TIMESTAMP,               -- Last activity timestamp
    metrics JSON,                           -- Agent performance metrics
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Changes from current schema**:
- ❌ **REMOVE** `project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE` (line 154)
- ✅ **ADD** `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP` for audit trail

**Rationale**:
- Agents are global resources, not scoped to a single project
- An agent like `backend-001` should be able to work on `project-1` today, `project-2` tomorrow
- `current_task_id` provides project context indirectly (via task's `project_id`)

---

### 1.2 New `project_agents` Junction Table

**Purpose**: Establish many-to-many relationship between projects and agents.

```sql
CREATE TABLE IF NOT EXISTS project_agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    role TEXT NOT NULL,                     -- Role in THIS project (e.g., "primary_backend", "code_reviewer")
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    unassigned_at TIMESTAMP,                -- NULL if still assigned
    is_active BOOLEAN DEFAULT TRUE,         -- Quick filter for currently assigned agents

    -- Prevent duplicate active assignments
    UNIQUE(project_id, agent_id, is_active) WHERE is_active = TRUE,

    -- Audit trail for reassignments
    CHECK(unassigned_at IS NULL OR unassigned_at >= assigned_at)
);
```

**Key Design Decisions**:

1. **Composite Unique Constraint with Partial Index**:
   - `UNIQUE(project_id, agent_id, is_active) WHERE is_active = TRUE`
   - Prevents same agent from being assigned to same project twice (while active)
   - Allows historical records (when `is_active = FALSE`)
   - **SQLite Note**: Partial unique indexes require SQLite 3.8.0+ (2013)

2. **Surrogate Primary Key (`id`)**:
   - Simplifies foreign key references if needed later
   - Enables historical tracking of assignments
   - Alternative: `PRIMARY KEY (project_id, agent_id)` if no history needed

3. **Soft Delete Pattern**:
   - `is_active` flag for quick filtering
   - `unassigned_at` timestamp for audit trail
   - Preserves historical assignments for analytics

4. **Role Field**:
   - Allows same agent to have different roles on different projects
   - Example: `backend-001` is "primary_backend" on Project A, "code_reviewer" on Project B
   - Values: `"primary_backend"`, `"secondary_backend"`, `"code_reviewer"`, `"consultant"`

---

### 1.3 Indexes for Query Performance

```sql
-- Index: Find all agents for a project (most common query)
CREATE INDEX IF NOT EXISTS idx_project_agents_project_active
ON project_agents(project_id, is_active)
WHERE is_active = TRUE;

-- Index: Find all projects for an agent
CREATE INDEX IF NOT EXISTS idx_project_agents_agent_active
ON project_agents(agent_id, is_active)
WHERE is_active = TRUE;

-- Index: Historical lookup by assignment date
CREATE INDEX IF NOT EXISTS idx_project_agents_assigned_at
ON project_agents(assigned_at);

-- Index: Unassigned agents (for reassignment queries)
CREATE INDEX IF NOT EXISTS idx_project_agents_unassigned
ON project_agents(unassigned_at)
WHERE unassigned_at IS NOT NULL;
```

**Index Strategy**:
- **Partial indexes** on `is_active = TRUE` reduce index size by 50-90%
- **Covering indexes** for hot queries (agent list, project list)
- **Composite indexes** match WHERE clause order

---

## 2. Database Methods

### 2.1 Agent-Project Assignment Methods

```python
def assign_agent_to_project(
    self,
    project_id: int,
    agent_id: str,
    role: str = "worker"
) -> int:
    """Assign an agent to a project.

    Args:
        project_id: Project ID
        agent_id: Agent ID
        role: Agent's role in this project

    Returns:
        Assignment ID

    Raises:
        sqlite3.IntegrityError: If agent already assigned to project (while active)
    """
    cursor = self.conn.cursor()
    cursor.execute(
        """
        INSERT INTO project_agents (project_id, agent_id, role, is_active)
        VALUES (?, ?, ?, TRUE)
        """,
        (project_id, agent_id, role)
    )
    self.conn.commit()
    return cursor.lastrowid


def get_agents_for_project(
    self,
    project_id: int,
    active_only: bool = True
) -> List[Dict[str, Any]]:
    """Get all agents assigned to a project.

    Args:
        project_id: Project ID
        active_only: If True, only return currently assigned agents

    Returns:
        List of agent dictionaries with assignment metadata
    """
    cursor = self.conn.cursor()

    query = """
        SELECT
            a.id AS agent_id,
            a.type,
            a.provider,
            a.maturity_level,
            a.status,
            a.current_task_id,
            a.last_heartbeat,
            pa.role,
            pa.assigned_at,
            pa.unassigned_at,
            pa.is_active
        FROM agents a
        JOIN project_agents pa ON a.id = pa.agent_id
        WHERE pa.project_id = ?
    """

    if active_only:
        query += " AND pa.is_active = TRUE"

    query += " ORDER BY pa.assigned_at DESC"

    cursor.execute(query, (project_id,))
    return [dict(row) for row in cursor.fetchall()]


def get_projects_for_agent(
    self,
    agent_id: str,
    active_only: bool = True
) -> List[Dict[str, Any]]:
    """Get all projects an agent is assigned to.

    Args:
        agent_id: Agent ID
        active_only: If True, only return active assignments

    Returns:
        List of project dictionaries with assignment metadata
    """
    cursor = self.conn.cursor()

    query = """
        SELECT
            p.id AS project_id,
            p.name,
            p.description,
            p.status,
            p.phase,
            pa.role,
            pa.assigned_at,
            pa.unassigned_at,
            pa.is_active
        FROM projects p
        JOIN project_agents pa ON p.id = pa.project_id
        WHERE pa.agent_id = ?
    """

    if active_only:
        query += " AND pa.is_active = TRUE"

    query += " ORDER BY pa.assigned_at DESC"

    cursor.execute(query, (agent_id,))
    return [dict(row) for row in cursor.fetchall()]


def remove_agent_from_project(
    self,
    project_id: int,
    agent_id: str
) -> int:
    """Remove an agent from a project (soft delete).

    Args:
        project_id: Project ID
        agent_id: Agent ID

    Returns:
        Number of rows affected (0 if not assigned, 1 if unassigned)
    """
    cursor = self.conn.cursor()
    cursor.execute(
        """
        UPDATE project_agents
        SET is_active = FALSE,
            unassigned_at = CURRENT_TIMESTAMP
        WHERE project_id = ?
          AND agent_id = ?
          AND is_active = TRUE
        """,
        (project_id, agent_id)
    )
    self.conn.commit()
    return cursor.rowcount


def get_agent_assignment(
    self,
    project_id: int,
    agent_id: str
) -> Optional[Dict[str, Any]]:
    """Get assignment details for a specific agent-project pair.

    Args:
        project_id: Project ID
        agent_id: Agent ID

    Returns:
        Assignment dictionary or None if not found
    """
    cursor = self.conn.cursor()
    cursor.execute(
        """
        SELECT
            id,
            project_id,
            agent_id,
            role,
            assigned_at,
            unassigned_at,
            is_active
        FROM project_agents
        WHERE project_id = ? AND agent_id = ?
        ORDER BY assigned_at DESC
        LIMIT 1
        """,
        (project_id, agent_id)
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def reassign_agent_role(
    self,
    project_id: int,
    agent_id: str,
    new_role: str
) -> int:
    """Update an agent's role on a project.

    Args:
        project_id: Project ID
        agent_id: Agent ID
        new_role: New role for the agent

    Returns:
        Number of rows affected
    """
    cursor = self.conn.cursor()
    cursor.execute(
        """
        UPDATE project_agents
        SET role = ?
        WHERE project_id = ?
          AND agent_id = ?
          AND is_active = TRUE
        """,
        (new_role, project_id, agent_id)
    )
    self.conn.commit()
    return cursor.rowcount


def get_available_agents(
    self,
    agent_type: Optional[str] = None,
    exclude_project_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Get agents available for assignment (not at capacity).

    Args:
        agent_type: Filter by agent type (optional)
        exclude_project_id: Exclude agents already on this project

    Returns:
        List of available agent dictionaries
    """
    cursor = self.conn.cursor()

    query = """
        SELECT
            a.*,
            COUNT(pa.id) AS active_assignments
        FROM agents a
        LEFT JOIN project_agents pa ON a.id = pa.agent_id
            AND pa.is_active = TRUE
    """

    params = []
    if exclude_project_id:
        query += " AND pa.project_id != ?"
        params.append(exclude_project_id)

    if agent_type:
        query += " WHERE a.type = ?"
        params.append(agent_type)

    query += """
        GROUP BY a.id
        HAVING active_assignments < 3  -- Max 3 projects per agent
        ORDER BY active_assignments ASC, a.last_heartbeat DESC
    """

    cursor.execute(query, params)
    return [dict(row) for row in cursor.fetchall()]
```

### 2.2 Updated Existing Methods

**Changes needed in `database.py`**:

1. **`create_agent()` (line 1112)**: No changes needed (doesn't use `project_id`)

2. **`get_agent()` (line 1141)**: No changes needed (doesn't use `project_id`)

3. **`list_agents()` (line 1155)**:
   - **Optional Enhancement**: Add project assignment counts
   ```python
   def list_agents(self, include_assignments: bool = False) -> List[Dict[str, Any]]:
       """List all agents.

       Args:
           include_assignments: If True, include active assignment counts

       Returns:
           List of agent dictionaries
       """
       cursor = self.conn.cursor()

       if include_assignments:
           cursor.execute("""
               SELECT
                   a.*,
                   COUNT(pa.id) AS active_assignments
               FROM agents a
               LEFT JOIN project_agents pa ON a.id = pa.agent_id
                   AND pa.is_active = TRUE
               GROUP BY a.id
               ORDER BY a.id
           """)
       else:
           cursor.execute("SELECT * FROM agents ORDER BY id")

       return [dict(row) for row in cursor.fetchall()]
   ```

4. **`update_agent()` (line 1166)**: No changes needed (doesn't use `project_id`)

---

## 3. Cascade Behavior & Data Integrity

### 3.1 Deletion Cascades

```sql
-- Project deletion: Remove all agent assignments
project_id REFERENCES projects(id) ON DELETE CASCADE

-- Agent deletion: Remove all project assignments
agent_id REFERENCES agents(id) ON DELETE CASCADE
```

**Rationale**:
- **Project deleted** → All agent assignments automatically removed (no orphaned assignments)
- **Agent deleted** → All project assignments automatically removed (clean up resources)

### 3.2 Orphaned Agents

**Policy**: Agents NOT assigned to any project are **allowed** and desirable.

**Use Cases**:
1. **Agent Pool**: Pre-created agents waiting for work
2. **Between Projects**: Agent finished Project A, not yet assigned to Project B
3. **Specialized Agents**: Security auditors, performance optimizers (used rarely)

**Query to find orphaned agents**:
```sql
SELECT a.*
FROM agents a
LEFT JOIN project_agents pa ON a.id = pa.agent_id AND pa.is_active = TRUE
WHERE pa.id IS NULL;
```

### 3.3 Task Assignment Integrity

**Current Constraint**: `tasks.assigned_to` is a TEXT field (not a foreign key).

**Recommendation**: Keep current design for now, but add application-level validation:

```python
def assign_task_to_agent(self, task_id: int, agent_id: str, project_id: int) -> None:
    """Assign a task to an agent.

    Validates that agent is assigned to the task's project.
    """
    # Verify agent is assigned to project
    assignment = self.get_agent_assignment(project_id, agent_id)
    if not assignment or not assignment['is_active']:
        raise ValueError(
            f"Agent {agent_id} is not assigned to project {project_id}. "
            f"Use assign_agent_to_project() first."
        )

    # Update task
    self.conn.execute(
        "UPDATE tasks SET assigned_to = ?, status = 'assigned' WHERE id = ?",
        (agent_id, task_id)
    )
    self.conn.commit()
```

---

## 4. Common Query Patterns

### 4.1 Dashboard: "Show me all agents working on Project X"
```sql
SELECT
    a.id,
    a.type,
    a.status,
    pa.role,
    COUNT(t.id) AS task_count
FROM agents a
JOIN project_agents pa ON a.id = pa.agent_id
LEFT JOIN tasks t ON t.assigned_to = a.id
    AND t.project_id = pa.project_id
    AND t.status IN ('assigned', 'in_progress')
WHERE pa.project_id = ?
  AND pa.is_active = TRUE
GROUP BY a.id, a.type, a.status, pa.role;
```

### 4.2 Agent Workload: "Show me all projects Agent Y is working on"
```sql
SELECT
    p.id,
    p.name,
    p.status,
    pa.role,
    COUNT(t.id) AS task_count
FROM projects p
JOIN project_agents pa ON p.id = pa.project_id
LEFT JOIN tasks t ON t.project_id = p.id
    AND t.assigned_to = pa.agent_id
    AND t.status IN ('assigned', 'in_progress')
WHERE pa.agent_id = ?
  AND pa.is_active = TRUE
GROUP BY p.id, p.name, p.status, pa.role;
```

### 4.3 Resource Allocation: "Find available backend agents for Project Z"
```sql
SELECT
    a.*,
    COUNT(pa.id) AS active_projects
FROM agents a
LEFT JOIN project_agents pa ON a.id = pa.agent_id
    AND pa.is_active = TRUE
WHERE a.type = 'backend'
  AND a.status != 'offline'
  AND a.id NOT IN (
      SELECT agent_id
      FROM project_agents
      WHERE project_id = ? AND is_active = TRUE
  )
GROUP BY a.id
HAVING active_projects < 3
ORDER BY active_projects ASC, a.last_heartbeat DESC;
```

### 4.4 Audit Trail: "Show assignment history for Project X"
```sql
SELECT
    pa.*,
    a.type AS agent_type,
    a.status AS current_agent_status
FROM project_agents pa
JOIN agents a ON pa.agent_id = a.id
WHERE pa.project_id = ?
ORDER BY pa.assigned_at DESC;
```

---

## 5. Migration Strategy (migration_009)

### 5.1 Migration Steps

```python
class AddProjectAgentsJunctionTable(BaseMigration):
    """Add project_agents junction table for many-to-many relationships."""

    def up(self, conn: sqlite3.Connection) -> None:
        cursor = conn.cursor()

        # Step 1: Create project_agents table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS project_agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                unassigned_at TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                CHECK(unassigned_at IS NULL OR unassigned_at >= assigned_at)
            )
        """)

        # Step 2: Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_project_agents_project_active
            ON project_agents(project_id, is_active)
            WHERE is_active = TRUE
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_project_agents_agent_active
            ON project_agents(agent_id, is_active)
            WHERE is_active = TRUE
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_project_agents_assigned_at
            ON project_agents(assigned_at)
        """)

        # Step 3: Create unique constraint (partial index)
        cursor.execute("""
            CREATE UNIQUE INDEX idx_project_agents_unique_active
            ON project_agents(project_id, agent_id, is_active)
            WHERE is_active = TRUE
        """)

        # Step 4: Migrate existing data (if agents table has project_id)
        cursor.execute("PRAGMA table_info(agents)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'project_id' in columns:
            # Migrate existing agent-project relationships
            cursor.execute("""
                INSERT INTO project_agents (project_id, agent_id, role, is_active)
                SELECT
                    project_id,
                    id,
                    'migrated',  -- Default role
                    TRUE
                FROM agents
                WHERE project_id IS NOT NULL
            """)

            # Step 5: Drop project_id from agents table
            cursor.execute("PRAGMA foreign_keys = OFF")

            cursor.execute("""
                CREATE TABLE agents_new (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    provider TEXT,
                    maturity_level TEXT CHECK(maturity_level IN ('directive', 'coaching', 'supporting', 'delegating')),
                    status TEXT CHECK(status IN ('idle', 'working', 'blocked', 'offline')),
                    current_task_id INTEGER REFERENCES tasks(id),
                    last_heartbeat TIMESTAMP,
                    metrics JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                INSERT INTO agents_new
                SELECT
                    id, type, provider, maturity_level, status,
                    current_task_id, last_heartbeat, metrics,
                    CURRENT_TIMESTAMP  -- Default created_at for existing agents
                FROM agents
            """)

            cursor.execute("DROP TABLE agents")
            cursor.execute("ALTER TABLE agents_new RENAME TO agents")

            cursor.execute("PRAGMA foreign_keys = ON")

        conn.commit()

    def down(self, conn: sqlite3.Connection) -> None:
        cursor = conn.cursor()

        # WARNING: Downgrade loses assignment history
        cursor.execute("PRAGMA foreign_keys = OFF")

        # Recreate agents table WITH project_id
        cursor.execute("""
            CREATE TABLE agents_new (
                id TEXT PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                provider TEXT,
                maturity_level TEXT CHECK(maturity_level IN ('directive', 'coaching', 'supporting', 'delegating')),
                status TEXT CHECK(status IN ('idle', 'working', 'blocked', 'offline')),
                current_task_id INTEGER REFERENCES tasks(id),
                last_heartbeat TIMESTAMP,
                metrics JSON
            )
        """)

        # Restore ONE project per agent (loses multi-project assignments)
        cursor.execute("""
            INSERT INTO agents_new
            SELECT
                a.id,
                pa.project_id,  -- Pick FIRST assignment
                a.type,
                a.provider,
                a.maturity_level,
                a.status,
                a.current_task_id,
                a.last_heartbeat,
                a.metrics
            FROM agents a
            LEFT JOIN (
                SELECT agent_id, project_id, MIN(assigned_at) AS first_assigned
                FROM project_agents
                WHERE is_active = TRUE
                GROUP BY agent_id
            ) pa ON a.id = pa.agent_id
        """)

        cursor.execute("DROP TABLE agents")
        cursor.execute("ALTER TABLE agents_new RENAME TO agents")

        # Drop junction table
        cursor.execute("DROP TABLE IF EXISTS project_agents")

        cursor.execute("PRAGMA foreign_keys = ON")
        conn.commit()

migration = AddProjectAgentsJunctionTable()
```

### 5.2 Migration Testing

**Test Cases**:
1. **New Database**: Create schema from scratch, verify constraints
2. **Existing Database (no data)**: Upgrade, verify table structure
3. **Existing Database (with data)**:
   - Upgrade: Migrate agent assignments to `project_agents`
   - Verify data integrity: All agents have assignments
   - Downgrade: Restore `project_id` (picking first assignment)
4. **Partial Indexes**: Verify SQLite version supports partial indexes (3.8.0+)

---

## 6. Performance Characteristics

### 6.1 Query Performance Estimates

| Query | Execution Time | Notes |
|-------|----------------|-------|
| Get agents for project (10 agents) | <5ms | Covered by `idx_project_agents_project_active` |
| Get projects for agent (5 projects) | <5ms | Covered by `idx_project_agents_agent_active` |
| Find available agents (100 total) | <20ms | Aggregation + partial index |
| Dashboard workload (all agents + tasks) | <50ms | 2 JOINs + aggregation |
| Assignment history (1000 records) | <30ms | Covered by `idx_project_agents_assigned_at` |

### 6.2 Storage Overhead

**Per Assignment**:
- Row size: ~120 bytes (4 int + 2 text + 2 timestamp + 1 bool)
- 1000 assignments = ~120 KB
- Indexes: ~80 KB (4 partial indexes)
- **Total**: ~200 KB per 1000 assignments

**Scalability**:
- 10 projects × 10 agents = 100 assignments (~20 KB)
- 100 projects × 50 agents = 5,000 assignments (~1 MB)

---

## 7. Implementation Checklist

### Phase 1: Migration (migration_009)
- [ ] Write `migration_009_add_project_agents.py`
- [ ] Add `project_agents` table with constraints
- [ ] Create 4 indexes (partial + composite)
- [ ] Migrate existing data if `agents.project_id` exists
- [ ] Drop `project_id` from `agents` table
- [ ] Write comprehensive migration tests (15+ test cases)

### Phase 2: Database Methods
- [ ] Add `assign_agent_to_project()`
- [ ] Add `get_agents_for_project()`
- [ ] Add `get_projects_for_agent()`
- [ ] Add `remove_agent_from_project()`
- [ ] Add `get_agent_assignment()`
- [ ] Add `reassign_agent_role()`
- [ ] Add `get_available_agents()`
- [ ] Update `list_agents()` to include assignment counts
- [ ] Write unit tests (50+ tests)

### Phase 3: Application-Level Changes
- [ ] Update `WorkerAgent.__init__()` to NOT require `project_id`
- [ ] Add `assign_to_project(project_id, role)` method to `WorkerAgent`
- [ ] Update task assignment logic to validate agent-project assignments
- [ ] Update API endpoints to use new methods
- [ ] Write integration tests (20+ tests)

### Phase 4: Frontend Updates
- [ ] Update Dashboard to show agents per project (not projects per agent)
- [ ] Add "Assign Agent" UI component
- [ ] Add "Agent Workload" view (projects per agent)
- [ ] Update TypeScript types for assignment metadata
- [ ] Write frontend tests (10+ tests)

---

## 8. Alternatives Considered

### Alternative 1: Keep `project_id` in `agents` table
**Rejected**: Violates reusability principle, prevents agents from working on multiple projects.

### Alternative 2: Use composite primary key in `project_agents`
```sql
PRIMARY KEY (project_id, agent_id)
```
**Rejected**: Loses historical tracking, complicates audit trail. Surrogate key (`id`) is more flexible.

### Alternative 3: Store assignments as JSON in `projects.config`
```json
{
  "agents": [
    {"id": "backend-001", "role": "primary_backend"}
  ]
}
```
**Rejected**: Loses foreign key constraints, indexing, query performance. Violates normalization.

### Alternative 4: Add `project_id` to `agents` table as nullable foreign key
```sql
project_id INTEGER REFERENCES projects(id)  -- NULL for unassigned agents
```
**Rejected**: Still only allows one project per agent. Doesn't solve multi-project problem.

---

## 9. References

- **Original Analysis**: `SCHEMA_ANALYSIS_REPORT.md` (python-expert findings)
- **Current Schema**: `codeframe/persistence/database.py` lines 152-163
- **Migration System**: `codeframe/persistence/migrations/README.md`
- **Testing Strategy**: `tests/persistence/test_migration_*.py` patterns

---

## 10. Sign-Off

**Schema Design**: System Architect
**Date**: 2025-12-03
**Status**: Ready for Phase 1 Implementation (migration_009)

**Next Step**: Implement `migration_009_add_project_agents.py` with comprehensive tests.
