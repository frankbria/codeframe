# Quick Start: Multi-Agent Coordination

A practical guide to using CodeFRAME's multi-agent coordination features to parallelize your development workflow.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [5-Minute Tutorial](#5-minute-tutorial)
3. [Understanding the Architecture](#understanding-the-architecture)
4. [Common Patterns](#common-patterns)
5. [Advanced Usage](#advanced-usage)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before starting, ensure you have:

- **CodeFRAME installed** with Sprint 4 (Multi-Agent Coordination) complete
- **Python 3.11+** installed
- **Anthropic API key** set in environment: `export ANTHROPIC_API_KEY=your_key_here`
- **Project initialized** with tasks defined in the database
- **MongoDB running** (if using production environment)

Verify your setup:

```bash
# Check Python version
python --version  # Should be 3.11 or higher

# Verify CodeFRAME installation
python -c "from codeframe.agents.agent_pool_manager import AgentPoolManager; print('✅ CodeFRAME ready')"

# Check your API key is set
echo $ANTHROPIC_API_KEY  # Should print your key
```

---

## 5-Minute Tutorial

This tutorial demonstrates creating an agent pool, assigning tasks, and watching agents work in parallel.

### Step 1: Initialize Your Project

```python
from codeframe.persistence.database import Database
from codeframe.agents.lead_agent import LeadAgent

# Initialize database
db = Database("codeframe.db")

# Get or create project
project = db.get_or_create_project(
    name="my-awesome-app",
    root_path="/path/to/my-awesome-app"
)
project_id = project["id"]
```

### Step 2: Create a Lead Agent with Agent Pool

The Lead Agent manages the agent pool and coordinates task execution:

```python
import os

# Create Lead Agent (automatically creates agent pool)
lead_agent = LeadAgent(
    project_id=project_id,
    db=db,
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    max_agents=10  # Maximum concurrent agents
)

# Access the agent pool manager
pool = lead_agent.agent_pool_manager
```

### Step 3: Create Worker Agents

Create agents of different types for specialized tasks:

```python
# Create backend agent (Python/FastAPI specialist)
backend_agent_id = pool.create_agent("backend")
print(f"Created: {backend_agent_id}")  # Output: backend-worker-001

# Create frontend agent (React/TypeScript specialist)
frontend_agent_id = pool.create_agent("frontend")
print(f"Created: {frontend_agent_id}")  # Output: frontend-specialist-001

# Create test agent (pytest/testing specialist)
test_agent_id = pool.create_agent("test")
print(f"Created: {test_agent_id}")  # Output: test-engineer-001

# Check agent pool status
status = pool.get_agent_status()
print(f"Active agents: {len(status)}")
for agent_id, info in status.items():
    print(f"  {agent_id}: {info['status']}")
```

### Step 4: Define Tasks with Dependencies

Create tasks with dependency relationships:

```python
# Task 1: Create database models (no dependencies)
task1_id = db.create_task(
    project_id=project_id,
    task_number="1",
    title="Create User and Post models",
    description="Define SQLAlchemy models for User and Post",
    status="pending",
    depends_on="[]"  # No dependencies
)

# Task 2: Create API routes (depends on Task 1)
task2_id = db.create_task(
    project_id=project_id,
    task_number="2",
    title="Create FastAPI routes for users",
    description="Implement GET/POST/PUT/DELETE endpoints",
    status="pending",
    depends_on=f"[{task1_id}]"  # Waits for task 1
)

# Task 3: Create frontend component (depends on Task 2)
task3_id = db.create_task(
    project_id=project_id,
    task_number="3",
    title="Create UserList React component",
    description="Display users in a table with CRUD actions",
    status="pending",
    depends_on=f"[{task2_id}]"  # Waits for task 2
)

# Task 4: Write tests (independent, can run in parallel)
task4_id = db.create_task(
    project_id=project_id,
    task_number="4",
    title="Write unit tests for models",
    description="Test User and Post model validation",
    status="pending",
    depends_on="[]"  # No dependencies
)
```

### Step 5: Start Multi-Agent Execution

Launch parallel task execution with automatic dependency resolution:

```python
import asyncio

async def run_multi_agent():
    # Start multi-agent execution
    summary = await lead_agent.start_multi_agent_execution(
        max_retries=3,        # Retry failed tasks up to 3 times
        max_concurrent=5,     # Run up to 5 tasks in parallel
        timeout=300           # 5-minute timeout
    )

    # Print execution summary
    print("\n🎉 Execution Complete!")
    print(f"Total tasks: {summary['total_tasks']}")
    print(f"Completed: {summary['completed']}")
    print(f"Failed: {summary['failed']}")
    print(f"Retries: {summary['retries']}")
    print(f"Time: {summary['execution_time']:.2f}s")

# Run the async execution
asyncio.run(run_multi_agent())
```

### Step 6: Watch on Dashboard

Open the CodeFRAME Dashboard to monitor real-time progress:

```bash
# Start the dashboard (in a separate terminal)
cd web-ui
npm start
```

Open **http://localhost:3000** and you'll see:

- **3 agents** working simultaneously
- **Task 1** and **Task 4** executing in parallel (no dependencies)
- **Task 2** showing "Waiting on Task 1" (blocked)
- **Task 3** showing "Waiting on Task 2" (blocked)
- **Auto-unblocking**: Task 2 starts immediately when Task 1 completes
- **Real-time updates**: Status changes appear instantly via WebSocket

---

## Understanding the Architecture

### Agent Types

CodeFRAME provides three specialized worker agent types:

| Agent Type | Specialization | Assigned When Task Contains |
|------------|----------------|----------------------------|
| **Backend** | Python, FastAPI, SQLAlchemy, database operations | `"model"`, `"api"`, `"database"`, `"backend"` |
| **Frontend** | React, TypeScript, JSX, component creation | `"component"`, `"UI"`, `"frontend"`, `"react"` |
| **Test** | pytest, unit tests, integration tests | `"test"`, `"pytest"`, `"testing"` |

Assignment is automatic based on task title/description keywords.

### Dependency Resolution

The **DependencyResolver** builds a Directed Acyclic Graph (DAG) from task dependencies:

1. **Build Graph**: Parses `depends_on` field (JSON array of task IDs)
2. **Detect Cycles**: Validates no circular dependencies exist
3. **Find Ready Tasks**: Returns tasks with all dependencies satisfied
4. **Auto-Unblock**: When task completes, finds dependent tasks that become ready

**Example Dependency Chain**:

```
Task 1 (Models)
   ↓
Task 2 (API Routes) ← depends_on: [1]
   ↓
Task 3 (Frontend) ← depends_on: [2]
```

### Agent Pool Lifecycle

```python
# Agent states: idle → busy → idle (or retired)

# 1. Create agent (state: idle)
agent_id = pool.create_agent("backend")

# 2. Assign task (state: idle → busy)
pool.mark_agent_busy(agent_id, task_id=5)

# 3. Agent executes task...

# 4. Task completes (state: busy → idle)
pool.mark_agent_idle(agent_id)
# tasks_completed counter increments

# 5. Agent can be reused or retired
pool.retire_agent(agent_id)  # Removed from pool
```

**Pool Management Benefits**:
- **Reuse**: Idle agents handle new tasks (no recreation overhead)
- **Tracking**: Monitor agent status and tasks completed
- **Resource Limits**: Enforce max_agents cap to prevent resource exhaustion

---

## Common Patterns

### Pattern 1: Parallel Independent Tasks

**Use Case**: Multiple features that don't depend on each other

```python
# All tasks run simultaneously
tasks = [
    ("1", "Create User authentication", "[]"),
    ("2", "Create Post CRUD endpoints", "[]"),
    ("3", "Create Comment system", "[]"),
    ("4", "Create Search API", "[]"),
]

for task_num, title, deps in tasks:
    db.create_task(
        project_id=project_id,
        task_number=task_num,
        title=title,
        description=f"Implement {title}",
        status="pending",
        depends_on=deps
    )

# Result: 4 agents work in parallel, no blocking
```

**Timeline**:
```
Agent 1: [=================] Task 1 (100s)
Agent 2: [=================] Task 2 (100s)
Agent 3: [=================] Task 3 (100s)
Agent 4: [=================] Task 4 (100s)
Total time: 100s (4x speedup!)
```

### Pattern 2: Sequential Pipeline

**Use Case**: Tasks must complete in strict order

```python
# Database migration pipeline
task1 = db.create_task(
    project_id=project_id,
    task_number="1",
    title="Create migration script",
    depends_on="[]"
)

task2 = db.create_task(
    project_id=project_id,
    task_number="2",
    title="Apply migration to dev DB",
    depends_on=f"[{task1}]"
)

task3 = db.create_task(
    project_id=project_id,
    task_number="3",
    title="Run data validation tests",
    depends_on=f"[{task2}]"
)

task4 = db.create_task(
    project_id=project_id,
    task_number="4",
    title="Apply migration to staging",
    depends_on=f"[{task3}]"
)

# Result: Tasks execute sequentially, one at a time
```

**Timeline**:
```
Agent 1: [====] Task 1 → [====] Task 2 → [====] Task 3 → [====] Task 4
Total time: 400s (no parallelization)
```

### Pattern 3: Fan-Out / Fan-In

**Use Case**: One task unlocks many, which converge to final task

```python
# Step 1: Shared foundation
schema_task = db.create_task(
    task_number="1",
    title="Define GraphQL schema",
    depends_on="[]"
)

# Step 2: Fan-out (multiple tasks depend on schema)
resolver_tasks = []
for entity in ["User", "Post", "Comment", "Like"]:
    task = db.create_task(
        task_number=f"{entity[0]}",
        title=f"Implement {entity} resolver",
        depends_on=f"[{schema_task}]"
    )
    resolver_tasks.append(task)

# Step 3: Fan-in (integration depends on all resolvers)
integration_task = db.create_task(
    task_number="I",
    title="Integration tests for all resolvers",
    depends_on=f"[{','.join(map(str, resolver_tasks))}]"
)

# Result: Schema completes, then 4 resolvers run in parallel,
#         then integration tests run
```

**Timeline**:
```
Agent 1:                      [=====] Schema
Agent 2:                             [=====] User resolver
Agent 3:                             [=====] Post resolver
Agent 4:                             [=====] Comment resolver
Agent 5:                             [=====] Like resolver
Agent 6:                                    [=====] Integration tests
Total time: ~300s (Schema + Resolver + Integration)
```

### Pattern 4: Mixed Parallel and Sequential

**Use Case**: Realistic feature development with both types

```python
# Backend tasks (sequential)
models_task = db.create_task(task_number="B1", title="Create models", depends_on="[]")
api_task = db.create_task(task_number="B2", title="Create API", depends_on=f"[{models_task}]")

# Frontend tasks (sequential, depends on API)
component_task = db.create_task(task_number="F1", title="Create UI component", depends_on=f"[{api_task}]")
integration_ui = db.create_task(task_number="F2", title="Wire up API calls", depends_on=f"[{component_task}]")

# Test tasks (parallel with backend until integration)
unit_tests = db.create_task(task_number="T1", title="Unit tests", depends_on="[]")
e2e_tests = db.create_task(task_number="T2", title="E2E tests", depends_on=f"[{integration_ui}]")

# Result: Models + unit tests run in parallel, then cascading completion
```

**Timeline**:
```
Backend:  [====] Models → [====] API
Frontend:                       [====] Component → [====] Integration
Test:     [====] Unit tests                        [====] E2E tests
```

---

## Advanced Usage

### Manual Agent Assignment

Override automatic assignment for specific tasks:

```python
# Get specific agent type
agent_id = pool.get_or_create_agent("frontend")

# Manually mark as busy
pool.mark_agent_busy(agent_id, task_id=42)

# Execute task manually
agent_instance = pool.get_agent_instance(agent_id)
task_dict = db.get_task(42)
await agent_instance.execute_task(task_dict)

# Mark idle when done
pool.mark_agent_idle(agent_id)
```

### Custom Dependency Validation

Validate dependencies before adding to database:

```python
from codeframe.agents.dependency_resolver import DependencyResolver

# Load all tasks
tasks = [Task(**t) for t in db.get_project_tasks(project_id)]

# Build dependency graph
resolver = DependencyResolver()
resolver.build_dependency_graph(tasks)

# Validate new dependency won't create cycle
is_valid = resolver.validate_dependency(
    task_id=5,
    depends_on_id=2
)

if is_valid:
    db.update_task(5, {"depends_on": "[2]"})
else:
    print("❌ Cannot add dependency: would create cycle")
```

### Agent Pool Introspection

Monitor agent pool metrics:

```python
# Get detailed status
status = pool.get_agent_status()

# Calculate metrics
total_agents = len(status)
busy_agents = sum(1 for s in status.values() if s['status'] == 'busy')
idle_agents = sum(1 for s in status.values() if s['status'] == 'idle')
total_tasks_completed = sum(s['tasks_completed'] for s in status.values())

print(f"Pool: {busy_agents}/{total_agents} busy, {total_tasks_completed} tasks completed")

# Find most productive agent
most_productive = max(status.items(), key=lambda x: x[1]['tasks_completed'])
print(f"Top performer: {most_productive[0]} ({most_productive[1]['tasks_completed']} tasks)")
```

### Programmatic Task Dependency Updates

Update dependencies dynamically:

```python
# Add dependency to existing task
task = db.get_task(task_id=10)
current_deps = json.loads(task.get("depends_on", "[]"))
current_deps.append(5)  # Add dependency on task 5
db.update_task(10, {"depends_on": json.dumps(current_deps)})

# Remove dependency
current_deps.remove(5)
db.update_task(10, {"depends_on": json.dumps(current_deps)})
```

---

## Troubleshooting

### Common Issues and Solutions

#### Issue: "Agent pool at maximum capacity"

**Symptoms**: `RuntimeError: Agent pool at maximum capacity (10 agents)`

**Causes**:
- Too many concurrent tasks
- Agents not being retired after use
- `max_agents` limit too low

**Solutions**:

```python
# Solution 1: Retire idle agents
status = pool.get_agent_status()
for agent_id, info in status.items():
    if info['status'] == 'idle':
        pool.retire_agent(agent_id)
        print(f"Retired idle agent: {agent_id}")

# Solution 2: Increase max_agents limit
lead_agent = LeadAgent(
    project_id=project_id,
    db=db,
    api_key=api_key,
    max_agents=20  # Increase from default 10
)

# Solution 3: Clear pool (for testing)
pool.clear()  # ⚠️  Removes all agents, use with caution
```

#### Issue: "Circular dependency detected"

**Symptoms**: `ValueError: Circular dependencies detected: 5 → 7 → 9 → 5`

**Causes**:
- Task A depends on B, B depends on C, C depends on A (cycle)

**Solutions**:

```python
# Use topological sort to find correct order
from codeframe.core.models import Task

tasks = [Task(**t) for t in db.get_project_tasks(project_id)]
resolver = DependencyResolver()
resolver.build_dependency_graph(tasks)

# Get suggested execution order
order = resolver.topological_sort()
if order is None:
    print("❌ Circular dependency exists!")

    # Find blocked tasks
    blocked = resolver.get_blocked_tasks()
    print(f"Blocked tasks: {blocked}")

    # Fix: Remove circular dependency
    # Example: Remove task 9's dependency on task 5
    db.update_task(9, {"depends_on": "[7]"})  # Remove 5
else:
    print(f"✅ Valid execution order: {order}")
```

#### Issue: WebSocket Disconnects

**Symptoms**: Dashboard stops updating, agents still working

**Causes**:
- Network interruption
- WebSocket server restarted
- Browser lost connection

**Solutions**:

The Dashboard automatically reconnects with exponential backoff:
- **1s delay** after first disconnect
- **2s, 4s, 8s...** up to **30s max** for subsequent reconnects
- **Full state resync** after reconnection

If reconnection fails repeatedly:

```bash
# 1. Check WebSocket server is running
curl http://localhost:8080/health  # Should return 200 OK

# 2. Restart WebSocket server
cd codeframe
python -m codeframe.ui.websocket_server

# 3. Check browser console for errors
# Open DevTools → Console → Look for WebSocket errors

# 4. Verify CORS settings (for remote dashboard)
# In codeframe/ui/websocket_server.py:
# origins=["http://localhost:3000", "http://your-domain.com"]
```

#### Issue: Tasks Not Auto-Unblocking

**Symptoms**: Task shows "Waiting on Task 5", but Task 5 is completed

**Causes**:
- Task status not updated in database
- Dependency resolver not notified of completion
- Database transaction not committed

**Solutions**:

```python
# 1. Verify task status in database
task5 = db.get_task(5)
print(f"Task 5 status: {task5['status']}")  # Should be "completed"

# 2. Manually trigger unblocking
from codeframe.agents.dependency_resolver import DependencyResolver

tasks = [Task(**t) for t in db.get_project_tasks(project_id)]
resolver = DependencyResolver()
resolver.build_dependency_graph(tasks)

unblocked = resolver.unblock_dependent_tasks(completed_task_id=5)
print(f"Unblocked tasks: {unblocked}")

# 3. Update task status to trigger cascade
db.update_task(5, {"status": "completed"})
```

#### Issue: Agent Execution Times Out

**Symptoms**: `asyncio.TimeoutError: Multi-agent execution timed out after 300s`

**Causes**:
- Tasks taking longer than expected
- Infinite loop in agent code
- External API calls hanging

**Solutions**:

```python
# Solution 1: Increase timeout
summary = await lead_agent.start_multi_agent_execution(
    timeout=600  # Increase to 10 minutes
)

# Solution 2: Check task execution logs
# Look for stuck tasks in logs
# Example: "Agent backend-worker-001 executing task 5" with no completion

# Solution 3: Emergency shutdown (if needed)
# The timeout automatically triggers emergency shutdown:
# - All agents retired
# - Pending tasks canceled
# - Database transactions rolled back
```

#### Issue: "No tasks found for project"

**Symptoms**: `ValueError: No tasks found for project 1`

**Causes**:
- Project has no tasks created
- Wrong project ID
- Tasks not committed to database

**Solutions**:

```python
# 1. Verify project ID
projects = db.get_all_projects()
print(f"Projects: {projects}")

# 2. Check task count
tasks = db.get_project_tasks(project_id)
print(f"Tasks for project {project_id}: {len(tasks)}")

# 3. Create tasks if missing
if not tasks:
    task_id = db.create_task(
        project_id=project_id,
        task_number="1",
        title="First task",
        description="Test task",
        status="pending",
        depends_on="[]"
    )
    print(f"Created task: {task_id}")
```

---

## Next Steps

**Now that you've mastered multi-agent coordination**:

1. **Explore Advanced Features**:
   - Subagent spawning (code reviewers, accessibility checkers)
   - Bottleneck detection in dashboard
   - Custom agent types

2. **Optimize Your Workflow**:
   - Analyze execution summaries to identify slow tasks
   - Adjust `max_concurrent` for optimal parallelization
   - Use dependency depth for priority scheduling

3. **Integrate with CI/CD**:
   - Automate multi-agent execution in GitHub Actions
   - Deploy completed tasks to staging automatically
   - Monitor agent performance metrics

4. **Read the Full Documentation**:
   - [spec.md](./spec.md) - Complete feature specification
   - [plan.md](./plan.md) - Implementation architecture
   - [tasks.md](./tasks.md) - Task breakdown and status

---

**Questions or Issues?**

- Check the [Troubleshooting](#troubleshooting) section above
- Review logs: `codeframe/logs/multi_agent_execution.log`
- Open an issue on GitHub with execution summary and logs

Happy parallel coding! 🚀
