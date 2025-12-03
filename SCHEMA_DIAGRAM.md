# Multi-Agent Schema Entity Relationship Diagram

## High-Level Architecture

```
┌─────────────────┐          ┌──────────────────────┐          ┌─────────────────┐
│    PROJECTS     │          │   PROJECT_AGENTS     │          │     AGENTS      │
│                 │          │   (Junction Table)   │          │                 │
│  id (PK)        │◄─────────┤  id (PK)             │─────────►│  id (PK)        │
│  name           │   1      │  project_id (FK)     │      n   │  type           │
│  description    │          │  agent_id (FK)       │          │  provider       │
│  workspace_path │          │  role                │          │  maturity_level │
│  status         │          │  assigned_at         │          │  status         │
│  phase          │          │  unassigned_at       │          │  current_task_id│
│  created_at     │          │  is_active           │          │  last_heartbeat │
└─────────────────┘          │                      │          │  metrics        │
         │                   │  UNIQUE(project_id,  │          │  created_at     │
         │                   │   agent_id, is_active)│         └─────────────────┘
         │ 1                 │   WHERE is_active    │                   │
         │                   └──────────────────────┘                   │
         │                                                               │
         │ n                                                         n   │
         │                                                               │
         ▼                                                               │
┌─────────────────┐                                                     │
│     TASKS       │                                                     │
│                 │                                                     │
│  id (PK)        │                                                     │
│  project_id (FK)│─────────────────────────────────────────────────────┘
│  title          │  (TEXT, not FK constraint, but logically references)
│  description    │  assigned_to ───┐
│  status         │                  │
│  assigned_to    │◄─────────────────┘ (Self-reference for validation)
│  priority       │
│  depends_on     │
│  created_at     │
│  completed_at   │
└─────────────────┘
```

## Key Relationships

### 1. Projects ←→ Agents (Many-to-Many)
- **Through**: `project_agents` junction table
- **Cardinality**: One project can have many agents, one agent can work on many projects
- **Example**:
  ```
  Project A ─┬─ backend-001 (role: "primary_backend")
             ├─ frontend-001 (role: "primary_frontend")
             └─ review-001 (role: "code_reviewer")

  backend-001 ─┬─ Project A (role: "primary_backend")
               ├─ Project B (role: "consultant")
               └─ Project C (role: "secondary_backend")
  ```

### 2. Projects → Tasks (One-to-Many)
- **Foreign Key**: `tasks.project_id → projects.id`
- **Cascade**: `ON DELETE CASCADE` (deleting project deletes all tasks)
- **Example**:
  ```
  Project A ─┬─ Task 1 (assigned_to: "backend-001")
             ├─ Task 2 (assigned_to: "frontend-001")
             └─ Task 3 (assigned_to: "backend-001")
  ```

### 3. Agents → Tasks (Logical Reference, No FK)
- **Reference**: `tasks.assigned_to = agents.id` (TEXT field, not FK)
- **Validation**: Application-level check ensures `assigned_to` agent is assigned to task's project
- **Why No FK?**: Allows task reassignment without FK constraint violations
- **Example**:
  ```
  backend-001 ─┬─ Task 1 (project_id: A)
               └─ Task 3 (project_id: A)

  Must ensure: backend-001 is in project_agents WHERE project_id=A AND is_active=TRUE
  ```

### 4. Agents → Current Task (One-to-One, Optional)
- **Foreign Key**: `agents.current_task_id → tasks.id`
- **Nullable**: `NULL` when agent is idle
- **Purpose**: Quick lookup of what agent is working on right now
- **Example**:
  ```
  backend-001.current_task_id = 42
  ↓
  Task 42 (project_id: A, title: "Implement auth")
  ```

## Data Flow Example

### Scenario: Assign `backend-001` to `Project A` and give it `Task 1`

```
Step 1: Create Agent (if not exists)
┌─────────────────────────────────────────────────────────┐
│ INSERT INTO agents (id, type, provider, status)        │
│ VALUES ('backend-001', 'backend', 'claude', 'idle')    │
└─────────────────────────────────────────────────────────┘
                           ↓
                    agents.id = 'backend-001'

Step 2: Assign Agent to Project
┌─────────────────────────────────────────────────────────┐
│ INSERT INTO project_agents                              │
│   (project_id, agent_id, role, is_active)              │
│ VALUES (1, 'backend-001', 'primary_backend', TRUE)     │
└─────────────────────────────────────────────────────────┘
                           ↓
           project_agents: (project_id=1, agent_id='backend-001')

Step 3: Assign Task to Agent
┌─────────────────────────────────────────────────────────┐
│ -- Validate agent is assigned to project               │
│ SELECT 1 FROM project_agents                           │
│ WHERE project_id = 1                                   │
│   AND agent_id = 'backend-001'                         │
│   AND is_active = TRUE                                 │
│                                                         │
│ -- If exists, update task                              │
│ UPDATE tasks                                           │
│ SET assigned_to = 'backend-001', status = 'assigned'  │
│ WHERE id = 42                                          │
└─────────────────────────────────────────────────────────┘
                           ↓
                tasks.assigned_to = 'backend-001'

Step 4: Agent Starts Working
┌─────────────────────────────────────────────────────────┐
│ UPDATE agents                                          │
│ SET current_task_id = 42,                             │
│     status = 'working',                               │
│     last_heartbeat = CURRENT_TIMESTAMP                │
│ WHERE id = 'backend-001'                              │
└─────────────────────────────────────────────────────────┘
                           ↓
        agents.current_task_id = 42, status = 'working'
```

## Query Patterns

### Query 1: "Show all agents working on Project A"
```sql
SELECT a.id, a.type, a.status, pa.role, a.current_task_id
FROM agents a
JOIN project_agents pa ON a.id = pa.agent_id
WHERE pa.project_id = 1
  AND pa.is_active = TRUE;
```
**Uses Index**: `idx_project_agents_project_active`

### Query 2: "Show all projects backend-001 is assigned to"
```sql
SELECT p.id, p.name, p.status, pa.role, pa.assigned_at
FROM projects p
JOIN project_agents pa ON p.id = pa.project_id
WHERE pa.agent_id = 'backend-001'
  AND pa.is_active = TRUE;
```
**Uses Index**: `idx_project_agents_agent_active`

### Query 3: "Show backend-001's current workload"
```sql
SELECT
    p.id AS project_id,
    p.name AS project_name,
    pa.role,
    COUNT(t.id) AS active_tasks
FROM projects p
JOIN project_agents pa ON p.id = pa.project_id
LEFT JOIN tasks t ON t.project_id = p.id
    AND t.assigned_to = 'backend-001'
    AND t.status IN ('assigned', 'in_progress')
WHERE pa.agent_id = 'backend-001'
  AND pa.is_active = TRUE
GROUP BY p.id, p.name, pa.role;
```
**Result Example**:
```
project_id | project_name | role             | active_tasks
-----------|--------------|------------------|-------------
1          | API Server   | primary_backend  | 3
2          | Dashboard    | consultant       | 1
3          | Mobile App   | code_reviewer    | 0
```

### Query 4: "Find available backend agents for Project B"
```sql
SELECT
    a.id,
    a.status,
    COUNT(pa.id) AS active_projects
FROM agents a
LEFT JOIN project_agents pa ON a.id = pa.agent_id
    AND pa.is_active = TRUE
WHERE a.type = 'backend'
  AND a.status != 'offline'
  AND a.id NOT IN (
      SELECT agent_id
      FROM project_agents
      WHERE project_id = 2 AND is_active = TRUE
  )
GROUP BY a.id, a.status
HAVING active_projects < 3  -- Max capacity
ORDER BY active_projects ASC;
```
**Result Example**:
```
id           | status   | active_projects
-------------|----------|----------------
backend-003  | idle     | 0
backend-002  | working  | 1
backend-001  | working  | 3  (at capacity, excluded by HAVING)
```

## Constraints Summary

| Table | Constraint | Purpose |
|-------|-----------|---------|
| `agents` | `PRIMARY KEY (id)` | Unique agent identifier |
| `project_agents` | `PRIMARY KEY (id)` | Surrogate key for assignments |
| `project_agents` | `FOREIGN KEY (project_id)` | Reference to projects table |
| `project_agents` | `FOREIGN KEY (agent_id)` | Reference to agents table |
| `project_agents` | `UNIQUE(project_id, agent_id, is_active) WHERE is_active = TRUE` | Prevent duplicate active assignments |
| `project_agents` | `CHECK(unassigned_at IS NULL OR unassigned_at >= assigned_at)` | Ensure logical timestamp ordering |
| `tasks` | `FOREIGN KEY (project_id)` | Reference to projects table |
| `agents` | `FOREIGN KEY (current_task_id)` | Optional reference to current task |

## Index Summary

| Index | Table | Columns | Type | Purpose |
|-------|-------|---------|------|---------|
| `idx_project_agents_project_active` | `project_agents` | `(project_id, is_active)` | Partial (WHERE is_active=TRUE) | Find agents for project |
| `idx_project_agents_agent_active` | `project_agents` | `(agent_id, is_active)` | Partial (WHERE is_active=TRUE) | Find projects for agent |
| `idx_project_agents_assigned_at` | `project_agents` | `(assigned_at)` | Regular | Assignment history queries |
| `idx_project_agents_unique_active` | `project_agents` | `(project_id, agent_id, is_active)` | Unique Partial (WHERE is_active=TRUE) | Enforce single active assignment |

## Migration Strategy

### Before Migration (Current State)
```
agents
  ├── id (PK)
  ├── project_id (FK) ← INCORRECT! To be removed
  ├── type
  └── ...

Result: One agent can only work on ONE project
```

### After Migration (Target State)
```
agents                    project_agents              projects
  ├── id (PK)              ├── id (PK)                 ├── id (PK)
  ├── type                 ├── project_id (FK) ────────┤
  └── ...                  ├── agent_id (FK) ──┐       └── ...
                           ├── role             │
                           ├── assigned_at      │
                           ├── unassigned_at    │
                           └── is_active        │
                                                │
                                                └──────► agents.id

Result: One agent can work on MULTIPLE projects
```

### Migration Data Flow
```
1. Read agents.project_id (if exists)
   ↓
2. INSERT INTO project_agents (project_id, agent_id, role)
   ↓
3. DROP project_id from agents table (recreate table)
   ↓
4. CREATE indexes on project_agents
```

## Performance Notes

- **Partial Indexes**: 50-90% smaller than full indexes (only index active assignments)
- **Join Cost**: 2-table join (agents + project_agents) is <5ms for 100 agents
- **Write Cost**: Assignment creation is 1 INSERT + 1 index update
- **Read Optimization**: Most queries use covering indexes (no table scan)

## Comparison: Before vs After

| Aspect | Before (project_id in agents) | After (project_agents junction) |
|--------|-------------------------------|----------------------------------|
| Agent reusability | ❌ One project only | ✅ Multiple projects |
| Historical tracking | ❌ No history | ✅ Full assignment history |
| Query complexity | ✅ Simple (1 table) | ⚠️ Moderate (2 tables, 1 JOIN) |
| Write overhead | ✅ Low (1 UPDATE) | ⚠️ Medium (1 INSERT + indexes) |
| Data normalization | ❌ Denormalized | ✅ Properly normalized |
| Scalability | ⚠️ Limited | ✅ Excellent |

## Recommendations

1. **Use partial indexes** - Reduce index size by 50-90%
2. **Add `created_at` to agents** - Track agent creation for analytics
3. **Keep `assigned_to` as TEXT** - Avoid FK constraint issues during reassignment
4. **Validate assignments at app level** - Ensure agent is assigned before task assignment
5. **Monitor assignment counts** - Prevent agent overload (max 3 projects per agent)
6. **Use soft deletes** - Preserve assignment history with `is_active` flag

---

**Diagram Generated**: 2025-12-03
**Next Step**: Implement migration_009 according to `MULTI_AGENT_SCHEMA_DESIGN.md`
