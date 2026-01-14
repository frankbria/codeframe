# Multi-Agent Execution Guide

## Overview

CodeFRAME's multi-agent system enables parallel execution of tasks across multiple specialized agents. Instead of processing tasks sequentially with a single agent, the system can run 3-5 agents concurrently, dramatically reducing project completion time.

### Key Benefits

- **⚡ Faster Execution**: 3-5x speedup with parallel processing
- **🎯 Specialized Agents**: Backend, frontend, and test agents optimized for specific tasks
- **🔗 Dependency Management**: Automatic handling of task dependencies
- **♻️ Agent Reuse**: Efficient resource utilization through agent pooling
- **📊 Real-Time Monitoring**: Live dashboard updates showing agent status and progress

### When to Use Multi-Agent

**Use multi-agent execution when**:
- Project has ≥5 tasks
- Tasks can be parallelized (independent or with clear dependencies)
- Mix of backend, frontend, and test tasks
- Time-sensitive delivery required

**Stick with single-agent when**:
- Project has <5 tasks
- All tasks are sequential (each depends on previous)
- Tasks are highly coupled
- Learning/experimentation phase

## Quick Start

### 1. Configure Task Dependencies

Dependencies tell the system which tasks must complete before others can start.

**Example: Building a User Management Feature**

```
Task 1: Create User Database Model         (no dependencies)
Task 2: Build User API Endpoints            (depends on Task 1)
Task 3: Create User Profile Component       (depends on Task 2)
Task 4: Write Unit Tests for User API       (depends on Task 2)
Task 5: Integration Test                    (depends on Tasks 3 and 4)
```

**In the Dashboard**:
1. Create all 5 tasks
2. For Task 2, set `depends_on` field to `"1"`
3. For Task 3, set `depends_on` field to `"2"`
4. For Task 4, set `depends_on` field to `"2"`
5. For Task 5, set `depends_on` field to `"3,4"`

### 2. Start Multi-Agent Execution

**Via API** (programmatic):
```bash
POST /api/projects/{project_id}/execute/multi-agent
{
  "max_concurrent": 3
}
```

**Via CLI**:
```bash
codeframe execute --multi-agent --max-concurrent 3
```

**Via Python**:
```python
from codeframe.agents.lead_agent import LeadAgent

lead = LeadAgent(project_id=1, db=db)
summary = await lead.start_multi_agent_execution(max_concurrent=3)

print(f"Completed: {summary['completed']}/{summary['total_tasks']}")
print(f"Failed: {summary['failed']}")
print(f"Time: {summary['execution_time']:.1f}s")
```

### 3. Monitor Progress

Watch the Dashboard to see:
- **Agent Cards**: Shows active agents (idle/busy/blocked)
- **Task List**: Real-time status updates (pending/in_progress/completed)
- **Dependency Indicators**: Visual badges showing blocked tasks
- **Activity Feed**: Live log of agent and task events

## Task Dependency Configuration

### Dependency Syntax

Dependencies are specified as comma-separated task IDs or task numbers:

```
"1"        → Depends on task 1
"1,2"      → Depends on tasks 1 and 2
"T-001"    → Depends on task T-001
"1,T-002"  → Depends on task 1 and task T-002
```

### Dependency Examples

**Sequential Dependencies** (waterfall):
```
Task 1: Design Database Schema        depends_on: ""
Task 2: Implement Database Models     depends_on: "1"
Task 3: Create API Endpoints          depends_on: "2"
Task 4: Build Frontend Components     depends_on: "3"
Task 5: Write Tests                   depends_on: "4"
```

**Parallel with Convergence**:
```
Task 1: Setup Infrastructure          depends_on: ""
Task 2: Backend Development           depends_on: "1"
Task 3: Frontend Development          depends_on: "1"
Task 4: Test Development              depends_on: "1"
Task 5: Integration Test              depends_on: "2,3,4"
```

**Complex Dependency Graph**:
```
Task 1: Database Schema               depends_on: ""
Task 2: User Model                    depends_on: "1"
Task 3: Post Model                    depends_on: "1"
Task 4: Comment Model                 depends_on: "1"
Task 5: User API                      depends_on: "2"
Task 6: Post API                      depends_on: "3"
Task 7: Comment API                   depends_on: "4"
Task 8: Frontend Components           depends_on: "5,6,7"
Task 9: Integration Tests             depends_on: "8"
```

### Circular Dependencies

**❌ Circular dependencies are automatically detected and rejected**:

```
Task 1 depends on Task 2
Task 2 depends on Task 1
→ Error: "Circular dependency detected"
```

**Common patterns that create cycles**:
- Task A → Task B → Task A (direct cycle)
- Task A → Task B → Task C → Task A (indirect cycle)
- Self-dependency: Task A → Task A

**Solution**: Review dependency chain and break the cycle by removing or reordering dependencies.

## Agent Types

### Backend Worker Agent

**Specializes in**:
- Python backend code (FastAPI, Flask, Django)
- Database models (SQLAlchemy)
- API endpoints and business logic
- Data validation and schemas

**Task Keywords**: "api", "backend", "database", "model", "endpoint", "service"

**Example Task**:
```
Title: "Create User API Endpoints"
Description: "Implement FastAPI endpoints for:
- POST /users (create user)
- GET /users/{id} (get user)
- PUT /users/{id} (update user)
- DELETE /users/{id} (delete user)

Include Pydantic schemas for request/response validation"
```

### Frontend Worker Agent

**Specializes in**:
- React components (TypeScript)
- Tailwind CSS styling
- UI/UX implementation
- Client-side state management

**Task Keywords**: "component", "frontend", "ui", "react", "interface", "page"

**Example Task**:
```
Title: "User Profile Component"
Description: "Create UserProfile React component that displays:
- User avatar (circular, 64px)
- Full name (heading)
- Email address
- Join date
- Edit button (opens edit modal)

Use Tailwind CSS for styling. Make it responsive."
```

### Test Worker Agent

**Specializes in**:
- Unit tests (pytest)
- Integration tests
- Test fixtures and mocks
- Self-correction (fixes failing tests automatically)

**Task Keywords**: "test", "testing", "pytest", "spec", "unittest"

**Example Task**:
```
Title: "Test User Service"
Description: "Create pytest tests for UserService class:
- test_create_user (valid data)
- test_create_user_invalid_email
- test_get_user_exists
- test_get_user_not_found
- test_update_user
- test_delete_user

Use fixtures for database setup/teardown"
```

## Agent Pool Management

### How Agent Reuse Works

The system maintains a pool of agents and reuses idle agents before creating new ones:

```
1. Task 1 (backend) → Creates backend-worker-001
2. Task 1 completes → backend-worker-001 marked idle
3. Task 2 (backend) → Reuses backend-worker-001 (no new agent created!)
4. Task 3 (frontend) → Creates frontend-specialist-001
5. Task 2 completes → backend-worker-001 marked idle again
6. Task 4 (backend) → Reuses backend-worker-001 (still just 2 agents total)
```

**Benefits**:
- Faster task assignment (~1ms vs ~100ms for new agent)
- Lower memory usage (~10MB per agent)
- Reduced API overhead (no new API clients)

### Maximum Concurrent Agents

Default: **10 agents maximum**

**Adjusting the limit**:

```python
# Increase for powerful machines
lead.start_multi_agent_execution(max_concurrent=15)

# Decrease for resource-constrained environments
lead.start_multi_agent_execution(max_concurrent=3)
```

**Guidelines**:
- **Low-resource (2-4 CPU cores)**: max_concurrent=3
- **Medium-resource (4-8 CPU cores)**: max_concurrent=5
- **High-resource (8+ CPU cores)**: max_concurrent=10

### Agent Lifecycle

```
┌─────────────┐
│   Created   │ → Agent instantiated, added to pool
└──────┬──────┘
       ↓
┌─────────────┐
│    Idle     │ → Waiting for task assignment
└──────┬──────┘
       ↓
┌─────────────┐
│    Busy     │ → Executing task
└──────┬──────┘
       ↓
┌─────────────┐
│    Idle     │ → Task complete, ready for new assignment
└──────┬──────┘
       ↓
┌─────────────┐
│   Retired   │ → Removed from pool, resources freed
└─────────────┘
```

**Agents are retired when**:
- All tasks completed
- Agent idle for extended period
- Pool cleanup initiated

## Execution Flow

### Typical Execution Sequence

```
1. Load all tasks from database
2. Build dependency graph
3. Detect circular dependencies (fail fast if found)
4. Enter coordination loop:

   While tasks remain:
     a. Get ready tasks (all dependencies satisfied)
     b. For each ready task (up to max_concurrent):
        - Determine agent type needed
        - Get or create agent from pool
        - Mark agent as busy
        - Execute task asynchronously
        - Mark task as in_progress
     c. Wait for running tasks
     d. Process completed tasks:
        - Mark task as completed
        - Mark agent as idle
        - Find newly unblocked tasks
     e. Handle failed tasks:
        - Retry (up to 3 attempts)
        - Mark as failed if max retries exceeded
     f. Check completion:
        - All tasks completed or failed?
        - Exit loop

5. Generate execution summary
6. Return results
```

### Execution States

**Task States**:
- `pending`: Not yet started, may have unsatisfied dependencies
- `blocked`: Dependencies not yet completed (shown with 🚫 badge)
- `assigned`: Assigned to agent, about to start
- `in_progress`: Currently executing
- `completed`: Successfully completed
- `failed`: Execution failed after retries

**Agent States**:
- `idle`: Available for task assignment (🟢 green)
- `busy`: Currently executing task (🟡 yellow)
- `blocked`: Waiting for task dependencies (🔴 red)

## Real-Time Dashboard

### Agent Cards

Each active agent displays:
- **Agent ID**: e.g., "backend-worker-001"
- **Agent Type**: Backend, Frontend, or Test
- **Status**: Idle (green), Busy (yellow), Blocked (red)
- **Current Task**: Task title if busy
- **Tasks Completed**: Running count

**Example**:
```
┌──────────────────────────────────┐
│ 🤖 backend-worker-001            │
│ Type: Backend Worker             │
│ Status: 🟡 Busy                  │
│ Current: Create User API         │
│ Completed: 3 tasks               │
└──────────────────────────────────┘
```

### Task List

Tasks show dependency information:
- **🔗 Icon**: Task has dependencies
- **🚫 Blocked Badge**: Dependencies not satisfied
- **Dependency Tooltip**: Hover to see dependency details
- **Color-Coded Borders**:
  - Green: Completed
  - Blue: In Progress
  - Red: Blocked
  - Gray: Pending

**Example**:
```
┌─────────────────────────────────────────┐
│ 🔗 T-003: Build User Profile Component │
│ Status: 🚫 Blocked                      │
│ ↳ 1 dependency: T-002 (in_progress)    │
└─────────────────────────────────────────┘
   Hover to see: T-002: Create User API (in_progress)
```

### Activity Feed

Live event stream showing:
- Agent lifecycle events (created, retired)
- Task status changes (started, completed, failed)
- Dependency events (blocked, unblocked)

**Example**:
```
23:55:12 | 🤖 Created backend-worker-001
23:55:13 | 📝 Task 1 started (backend-worker-001)
23:55:45 | ✅ Task 1 completed
23:55:45 | 🔓 Task 2 unblocked (dependency satisfied)
23:55:46 | 📝 Task 2 started (backend-worker-001)
```

## Troubleshooting

### Tasks Not Starting

**Symptom**: Tasks remain in "pending" state

**Possible Causes**:
1. **Dependencies not satisfied**
   - Check if dependent tasks are completed
   - Look for 🚫 Blocked badge
   - Hover over dependency indicator for details

2. **Circular dependency**
   - Review error logs for "Circular dependency detected"
   - Check dependency chain: A→B→C→A
   - Break the cycle by removing/reordering dependencies

3. **All agents busy**
   - Check agent status cards
   - Wait for agents to become idle
   - Or increase `max_concurrent` limit

**Solution**:
```
1. Open Dashboard
2. Check task dependency indicators (🔗 icon)
3. Hover over dependency count to see details
4. Verify dependent tasks are completed
5. If stuck, check logs for circular dependency errors
```

### Performance Issues

**Symptom**: Execution slower than expected

**Possible Causes**:
1. **Too many concurrent agents**
   - System overloaded (high CPU/memory)
   - Network throttling (API rate limits)

2. **Sequential dependencies**
   - Tasks can't run in parallel
   - Dependency chain too long

3. **Resource-intensive tasks**
   - Large code generation
   - Many test executions

**Solutions**:
```python
# Reduce concurrent agents
lead.start_multi_agent_execution(max_concurrent=3)  # Instead of 10

# Review dependencies - can tasks be parallelized?
# Example: Instead of this (sequential):
#   Task 2 depends on Task 1
#   Task 3 depends on Task 2
#   Task 4 depends on Task 3

# Try this (parallel):
#   Task 2, 3, 4 all depend on Task 1
#   (they can run simultaneously)
```

### Agent Failures

**Symptom**: Tasks fail with agent errors

**Common Errors**:

1. **API Rate Limit**
   ```
   Error: Rate limit exceeded
   Solution: Wait 60s, reduce max_concurrent
   ```

2. **Invalid Task Specification**
   ```
   Error: Could not generate code from description
   Solution: Provide clearer task description with examples
   ```

3. **File Conflict**
   ```
   Error: File already exists
   Solution: Check for duplicate tasks or merge conflicts
   ```

### Dependency Deadlock

**Symptom**: Tasks stuck in "blocked" state indefinitely

**Cause**: Circular dependency not detected (rare edge case)

**Solution**:
```
1. Identify blocked tasks in Dashboard
2. Check their dependencies
3. Look for cycle: Task A blocks Task B which blocks Task A
4. Remove circular dependency
5. Restart execution
```

## Best Practices

### 1. Task Granularity

**✅ Good - Right-sized tasks**:
```
Task 1: "Create User model with name, email, password fields"
Task 2: "Implement User API endpoints (CRUD)"
Task 3: "Create UserCard component showing user info"
```

**❌ Bad - Tasks too large**:
```
Task 1: "Build entire user management system"
```

**❌ Bad - Tasks too small**:
```
Task 1: "Add name field to User model"
Task 2: "Add email field to User model"
Task 3: "Add password field to User model"
```

**Rule of Thumb**: Each task should take 3-15 minutes for an agent to complete.

### 2. Dependency Planning

**✅ Good - Maximize parallelism**:
```
Task 1: Setup (no dependencies)
Task 2, 3, 4: Parallel work (all depend on Task 1)
Task 5: Integration (depends on Tasks 2, 3, 4)
```

**❌ Bad - Unnecessary sequence**:
```
Task 1 → Task 2 → Task 3 → Task 4 → Task 5
(Could be parallelized but forced sequential)
```

**Strategy**: Draw dependency graph on paper first to visualize parallel opportunities.

### 3. Clear Task Descriptions

**✅ Good - Specific requirements**:
```
Title: "UserCard Component"
Description: "Create React component displaying:
- Avatar (circular, 48px, from user.avatar_url)
- Name (bold, 16px, user.full_name)
- Email (gray, 14px, user.email)
- Role badge (colored: admin=red, user=blue)
Style with Tailwind. Make responsive (mobile/desktop)."
```

**❌ Bad - Vague description**:
```
Title: "User component"
Description: "Make a component for users"
```

### 4. Monitor and Iterate

1. **Start with conservative settings**:
   ```python
   max_concurrent=3  # Start small
   ```

2. **Monitor first execution**:
   - Watch agent utilization
   - Check for bottlenecks
   - Note execution time

3. **Adjust based on results**:
   ```python
   # If agents mostly idle → increase concurrency
   max_concurrent=5

   # If system overloaded → decrease concurrency
   max_concurrent=2
   ```

4. **Optimize dependencies**:
   - Identify sequential bottlenecks
   - Look for parallelization opportunities
   - Reorganize tasks if needed

### 5. Error Recovery

**Enable retries** (default: 3 attempts):
```python
lead.start_multi_agent_execution(max_retries=3)
```

**Handle partial failures**:
```python
summary = await lead.start_multi_agent_execution()

if summary['failed'] > 0:
    print(f"Warning: {summary['failed']} tasks failed")
    # Review failed tasks
    # Fix issues
    # Re-run failed tasks only
```

## Advanced Features

### Custom Agent Configuration

```python
from codeframe.agents.agent_pool_manager import AgentPoolManager

# Create custom pool
pool = AgentPoolManager(
    project_id=1,
    db=db,
    max_agents=15,  # Higher limit
    api_key="custom-key"  # Custom API key
)

# Pass to LeadAgent
lead = LeadAgent(
    project_id=1,
    db=db,
    agent_pool_manager=pool  # Use custom pool
)
```

### Programmatic Monitoring

```python
import asyncio

async def monitor_execution():
    """Monitor execution progress in real-time."""

    lead = LeadAgent(project_id=1, db=db)

    # Start execution (non-blocking)
    execution_task = asyncio.create_task(
        lead.start_multi_agent_execution()
    )

    # Monitor while running
    while not execution_task.done():
        status = lead.agent_pool_manager.get_agent_status()

        print(f"Active agents: {len(status)}")
        for agent_id, info in status.items():
            print(f"  {agent_id}: {info['status']} - {info['tasks_completed']} completed")

        await asyncio.sleep(5)  # Check every 5 seconds

    # Get final summary
    summary = await execution_task
    print(f"Execution complete: {summary}")

await monitor_execution()
```

### Custom Dependency Validation

```python
from codeframe.agents.dependency_resolver import DependencyResolver

# Validate dependencies before execution
resolver = DependencyResolver(tasks)

try:
    resolver.build_dependency_graph()
    print("✅ Dependency graph valid - no cycles")
except ValueError as e:
    print(f"❌ Invalid dependencies: {e}")
    # Fix dependencies
```

## Examples

### Example 1: E-Commerce Feature

**Scenario**: Build product catalog feature with backend API, frontend UI, and tests.

**Tasks**:
```
Task 1: Product Database Model
  depends_on: ""
  description: "Create Product model with name, price, description, image_url, stock"

Task 2: Product API Endpoints
  depends_on: "1"
  description: "Implement FastAPI endpoints:
    - GET /products (list with pagination)
    - GET /products/{id}
    - POST /products (admin only)
    - PUT /products/{id} (admin only)
    - DELETE /products/{id} (admin only)"

Task 3: ProductCard Component
  depends_on: "2"
  description: "Create ProductCard React component:
    - Product image (200x200)
    - Product name (heading)
    - Price (green, bold)
    - Add to Cart button
    Tailwind CSS styling"

Task 4: ProductList Component
  depends_on: "2"
  description: "Create ProductList React component:
    - Grid layout (3 columns desktop, 1 mobile)
    - Uses ProductCard components
    - Pagination controls
    - Loading state"

Task 5: Product API Tests
  depends_on: "2"
  description: "pytest tests for Product API:
    - test_list_products
    - test_get_product
    - test_create_product_admin
    - test_create_product_unauthorized
    - test_update_product
    - test_delete_product"

Task 6: Integration Test
  depends_on: "3,4,5"
  description: "End-to-end test:
    - Create products via API
    - Verify display in ProductList
    - Test Add to Cart flow"
```

**Execution**:
```python
# Will execute as:
# Step 1: Task 1 (backend agent)
# Step 2: Task 2 (backend agent, reuses same agent)
# Step 3: Tasks 3, 4, 5 in parallel (frontend, frontend, test agents)
# Step 4: Task 6 (test agent)

summary = await lead.start_multi_agent_execution(max_concurrent=3)
# Expected time: ~2-3 minutes
# Agents created: 3 (backend, frontend, test)
# Parallel speedup: ~2x (tasks 3,4,5 run simultaneously)
```

## Frequently Asked Questions

### Q: How do I know which agent type will handle my task?

**A**: Task assignment is automatic based on keywords in the task title/description:
- **Backend**: "api", "backend", "database", "model", "endpoint"
- **Frontend**: "component", "ui", "frontend", "react", "page"
- **Test**: "test", "pytest", "spec", "unittest"

### Q: Can I force a specific agent type?

**A**: Yes, use explicit keywords in the title:
```
"[Backend] Create User Service"  → Forces backend agent
"[Frontend] Build Dashboard"     → Forces frontend agent
"[Test] API Integration Tests"   → Forces test agent
```

### Q: What happens if an agent fails?

**A**: The system automatically retries the task up to 3 times. If all retries fail, the task is marked as "failed" and execution continues with other tasks.

### Q: Do I need to manually clean up agents?

**A**: No, agents are automatically retired when all tasks complete or after being idle for an extended period.

### Q: Can I run multi-agent execution multiple times on the same project?

**A**: Yes, you can run execution multiple times. The system only executes pending tasks and respects already-completed tasks.

### Q: How do I debug a blocked task?

**A**:
1. Check the Dashboard for 🚫 Blocked badge
2. Hover over the dependency indicator to see which tasks are blocking
3. Verify those tasks are progressing or completed
4. Check logs for circular dependency errors

## Next Steps

- **[API Reference](../api/README.md)**: Detailed API documentation
- **[DependencyResolver API](../api/dependency_resolver.md)**: Dependency management
- **[AgentPoolManager API](../api/agent_pool_manager.md)**: Agent pool configuration
- **[Worker Agents API](../api/worker_agents.md)**: Agent-specific documentation

## Support

Having issues with multi-agent execution?

- Check the [Troubleshooting](#troubleshooting) section above
- Review [API Documentation](../api/README.md) for detailed technical info
- Open an issue on [GitHub](https://github.com/frankbria/codeframe/issues)

---

**Last Updated**: 2025-10-26
**Version**: Sprint 4 (Multi-Agent Coordination)
