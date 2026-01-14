# Quick Reference: Agent-Project Assignment API

## TL;DR

**Before**: One agent per project (broken architecture)
```python
agent = WorkerAgent(agent_id="backend-001", project_id=1)  # ❌ Locked to project 1
```

**After**: Agents can work on multiple projects
```python
agent = WorkerAgent(agent_id="backend-001")  # ✅ Reusable resource
agent.assign_to_project(project_id=1, role="primary_backend")
agent.assign_to_project(project_id=2, role="consultant")
```

---

## Python API Quick Reference

### 1. Agent Lifecycle

```python
from codeframe.persistence.database import Database

db = Database("state.db")
db.initialize()

# Create an agent (reusable resource)
from codeframe.core.models import AgentMaturity

agent_id = db.create_agent(
    agent_id="backend-001",
    agent_type="backend",
    provider="claude",
    maturity_level=AgentMaturity.D4  # Use enum member, not string
)

# Assign to projects
db.assign_agent_to_project(
    project_id=1,
    agent_id="backend-001",
    role="primary_backend"
)

db.assign_agent_to_project(
    project_id=2,
    agent_id="backend-001",
    role="code_reviewer"
)
```

### 2. Querying Assignments

```python
# Find all agents on a project
agents = db.get_agents_for_project(project_id=1, active_only=True)
for agent in agents:
    print(f"{agent['agent_id']}: {agent['role']}")

# Find all projects for an agent
projects = db.get_projects_for_agent(agent_id="backend-001", active_only=True)
for project in projects:
    print(f"Project {project['project_id']}: {project['role']}")

# Check specific assignment
assignment = db.get_agent_assignment(project_id=1, agent_id="backend-001")
if assignment and assignment['is_active']:
    print(f"Active assignment: {assignment['role']}")
```

### 3. Task Assignment (with validation)

```python
# ❌ OLD WAY (no validation)
db.conn.execute(
    "UPDATE tasks SET assigned_to = ? WHERE id = ?",
    ("backend-001", 42)
)

# ✅ NEW WAY (validates agent is on project)
def assign_task_to_agent(db, task_id, agent_id, project_id):
    # Validate agent is assigned to project
    assignment = db.get_agent_assignment(project_id, agent_id)
    if not assignment or not assignment['is_active']:
        raise ValueError(
            f"Agent {agent_id} not assigned to project {project_id}"
        )

    # Update task
    db.conn.execute(
        "UPDATE tasks SET assigned_to = ?, status = 'assigned' WHERE id = ?",
        (agent_id, task_id)
    )
    db.conn.commit()

assign_task_to_agent(db, task_id=42, agent_id="backend-001", project_id=1)
```

### 4. Removing Assignments (Soft Delete)

```python
# Remove agent from project (soft delete)
rows = db.remove_agent_from_project(project_id=1, agent_id="backend-001")
if rows > 0:
    print("Agent unassigned successfully")
else:
    print("Agent was not assigned to this project")

# Agent still exists, just not assigned to this project
agent = db.get_agent("backend-001")
print(f"Agent status: {agent['status']}")  # Still exists!
```

### 5. Finding Available Agents

```python
# Find available backend agents (not at capacity)
available = db.get_available_agents(
    agent_type="backend",
    exclude_project_id=1  # Not already on project 1
)

for agent in available:
    print(f"{agent['id']}: {agent['active_assignments']} active projects")
```

---

## SQL Queries Quick Reference

### Show All Agents for Project 1
```sql
SELECT
    a.id,
    a.type,
    a.status,
    pa.role,
    pa.assigned_at
FROM agents a
JOIN project_agents pa ON a.id = pa.agent_id
WHERE pa.project_id = 1
  AND pa.is_active = TRUE;
```

### Show All Projects for Agent "backend-001"
```sql
SELECT
    p.id,
    p.name,
    p.status,
    pa.role,
    pa.assigned_at
FROM projects p
JOIN project_agents pa ON p.id = pa.project_id
WHERE pa.agent_id = 'backend-001'
  AND pa.is_active = TRUE;
```

### Show Agent Workload (Tasks per Project)
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

### Find Unassigned Agents (Agent Pool)
```sql
SELECT a.*
FROM agents a
LEFT JOIN project_agents pa ON a.id = pa.agent_id
    AND pa.is_active = TRUE
WHERE pa.id IS NULL
  AND a.status != 'offline';
```

### Show Assignment History for Project 1
```sql
SELECT
    pa.*,
    a.type AS agent_type,
    a.status AS current_status
FROM project_agents pa
JOIN agents a ON pa.agent_id = a.id
WHERE pa.project_id = 1
ORDER BY pa.assigned_at DESC;
```

---

## REST API Quick Reference

### Assign Agent to Project
```http
POST /api/projects/1/agents
Content-Type: application/json

{
  "agent_id": "backend-001",
  "role": "primary_backend"
}

Response: 201 Created
{
  "assignment_id": 42,
  "project_id": 1,
  "agent_id": "backend-001",
  "role": "primary_backend",
  "assigned_at": "2025-12-03T10:30:00Z",
  "is_active": true
}
```

### Get Agents for Project
```http
GET /api/projects/1/agents?is_active=true

Response: 200 OK
[
  {
    "agent_id": "backend-001",
    "type": "backend",
    "status": "working",
    "role": "primary_backend",
    "assigned_at": "2025-12-03T10:30:00Z",
    "current_task_id": 42,
    "is_active": true
  },
  {
    "agent_id": "frontend-001",
    "type": "frontend",
    "status": "idle",
    "role": "primary_frontend",
    "assigned_at": "2025-12-03T11:00:00Z",
    "current_task_id": null,
    "is_active": true
  }
]
```

### Get Projects for Agent
```http
GET /api/agents/backend-001/projects?is_active=true

Response: 200 OK
[
  {
    "project_id": 1,
    "name": "API Server",
    "status": "active",
    "phase": "active",
    "role": "primary_backend",
    "assigned_at": "2025-12-03T10:30:00Z",
    "is_active": true
  },
  {
    "project_id": 2,
    "name": "Dashboard",
    "status": "active",
    "phase": "planning",
    "role": "consultant",
    "assigned_at": "2025-12-03T12:00:00Z",
    "is_active": true
  }
]
```

### Remove Agent from Project
```http
DELETE /api/projects/1/agents/backend-001

Response: 204 No Content
```

### Update Agent Role
```http
PUT /api/projects/1/agents/backend-001/role
Content-Type: application/json

{
  "role": "code_reviewer"
}

Response: 200 OK
{
  "project_id": 1,
  "agent_id": "backend-001",
  "role": "code_reviewer",
  "assigned_at": "2025-12-03T10:30:00Z",
  "is_active": true
}
```

---

## Common Patterns

### Pattern 1: Onboarding New Agent to Project
```python
# Step 1: Create agent (if not exists)
agent_id = "backend-002"
if not db.get_agent(agent_id):
    db.create_agent(
        agent_id=agent_id,
        agent_type="backend",
        provider="claude",
        maturity_level="coaching"
    )

# Step 2: Assign to project
db.assign_agent_to_project(
    project_id=1,
    agent_id=agent_id,
    role="secondary_backend"
)

# Step 3: Assign first task
first_task = db.get_next_task(project_id=1, agent_type="backend")
assign_task_to_agent(db, first_task['id'], agent_id, project_id=1)
```

### Pattern 2: Rebalancing Workload
```python
# Find overloaded agents
agents = db.get_agents_for_project(project_id=1)
for agent in agents:
    tasks = db.get_tasks(project_id=1, assigned_to=agent['agent_id'], status='assigned')
    if len(tasks) > 5:
        print(f"{agent['agent_id']} is overloaded with {len(tasks)} tasks")

        # Find available agent
        available = db.get_available_agents(agent_type=agent['type'])
        if available:
            new_agent = available[0]
            # Assign new agent to project
            db.assign_agent_to_project(project_id=1, agent_id=new_agent['id'])

            # Reassign half the tasks
            for task in tasks[:len(tasks)//2]:
                assign_task_to_agent(db, task['id'], new_agent['id'], project_id=1)
```

### Pattern 3: Agent Rotation (Sprint Boundary)
```python
# Remove outgoing agent
db.remove_agent_from_project(project_id=1, agent_id="backend-001")

# Reassign their tasks to incoming agent
db.assign_agent_to_project(project_id=1, agent_id="backend-002", role="primary_backend")

tasks = db.get_tasks(project_id=1, assigned_to="backend-001", status='assigned')
for task in tasks:
    assign_task_to_agent(db, task['id'], "backend-002", project_id=1)
```

---

## Testing Quick Reference

### Unit Test: Assignment Validation
```python
def test_assign_agent_to_multiple_projects(db):
    # Create agent
    agent_id = "backend-001"
    db.create_agent(agent_id, "backend", "claude", "delegating")

    # Assign to multiple projects
    db.assign_agent_to_project(project_id=1, agent_id=agent_id, role="primary")
    db.assign_agent_to_project(project_id=2, agent_id=agent_id, role="consultant")

    # Verify assignments
    projects = db.get_projects_for_agent(agent_id)
    assert len(projects) == 2
    assert projects[0]['project_id'] in [1, 2]
    assert projects[1]['project_id'] in [1, 2]

def test_duplicate_assignment_fails(db):
    agent_id = "backend-001"
    db.create_agent(agent_id, "backend", "claude", "delegating")

    # First assignment succeeds
    db.assign_agent_to_project(project_id=1, agent_id=agent_id, role="primary")

    # Second assignment to same project fails
    with pytest.raises(sqlite3.IntegrityError):
        db.assign_agent_to_project(project_id=1, agent_id=agent_id, role="primary")

def test_task_assignment_requires_project_membership(db):
    agent_id = "backend-001"
    db.create_agent(agent_id, "backend", "claude", "delegating")

    # Create task on project 1
    task_id = db.create_task(project_id=1, title="Test task")

    # Assign task to agent NOT on project (should fail)
    with pytest.raises(ValueError, match="not assigned to project"):
        assign_task_to_agent(db, task_id, agent_id, project_id=1)

    # Assign agent to project, then task assignment succeeds
    db.assign_agent_to_project(project_id=1, agent_id=agent_id)
    assign_task_to_agent(db, task_id, agent_id, project_id=1)  # ✅ Success
```

---

## Migration Checklist

**Before migrating production database**:

- [ ] Backup database: `cp state.db state.db.backup`
- [ ] Run migration programmatically:
  ```python
  from codeframe.persistence.migrations import MigrationRunner
  from codeframe.persistence.migrations.migration_009_add_project_agents import migration

  runner = MigrationRunner(db_path="state.db")
  runner.register(migration)
  runner.apply_all()
  ```
- [ ] Verify schema: `sqlite3 state.db ".schema project_agents"`
- [ ] Check indexes: `sqlite3 state.db ".indexes project_agents"`
- [ ] Validate data: Query `project_agents` table for migrated assignments
- [ ] Update application code: Remove `project_id` from `WorkerAgent.__init__()`
- [ ] Run full test suite: `pytest tests/ -v`
- [ ] Test API endpoints: `curl http://localhost:8000/api/projects/1/agents`

---

## Troubleshooting

### Issue: "UNIQUE constraint failed: project_agents.project_id, project_agents.agent_id, project_agents.is_active"
**Cause**: Trying to assign same agent to same project twice (while active).
**Solution**: Check if agent already assigned before calling `assign_agent_to_project()`:
```python
assignment = db.get_agent_assignment(project_id, agent_id)
if not assignment or not assignment['is_active']:
    db.assign_agent_to_project(project_id, agent_id, role)
```

### Issue: "Agent not assigned to project" when assigning task
**Cause**: Agent exists but not assigned to task's project.
**Solution**: Assign agent to project first:
```python
db.assign_agent_to_project(project_id=1, agent_id="backend-001")
assign_task_to_agent(db, task_id=42, agent_id="backend-001", project_id=1)
```

### Issue: SQLite error "no such table: project_agents"
**Cause**: Migration not run yet.
**Solution**: Run migration programmatically:
```python
from codeframe.persistence.migrations import MigrationRunner
from codeframe.persistence.migrations.migration_009_add_project_agents import migration

runner = MigrationRunner(db_path="state.db")
runner.register(migration)
runner.apply_all()
```

### Issue: "table agents has no column named project_id"
**Cause**: Already migrated, but code still references old column.
**Solution**: Update code to remove `project_id` references in `agents` table queries.

---

## References

- **Full Schema Design**: `MULTI_AGENT_SCHEMA_DESIGN.md`
- **Visual Diagrams**: `SCHEMA_DIAGRAM.md`
- **Migration Code**: `codeframe/persistence/migrations/migration_009_add_project_agents.py`
- **Database Methods**: `codeframe/persistence/database.py` lines 1200+

---

**Last Updated**: 2025-12-03
**Status**: Ready for Implementation
