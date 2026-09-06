# Sprint 4 Multi-Agent Coordination - Manual Test Checklist

## Pre-Demo Setup Verification

### 1. Environment Check
- [ ] Verify staging server is running: `pm2 list`
  - [ ] Backend status: **online** (port 14200)
  - [ ] Frontend status: **online** (port 14100)
- [ ] Check backend health: `curl http://localhost:14200/`
  - Expected: `{"status":"online","service":"CodeFRAME Status Server"}`
- [ ] Check frontend loads: Open http://localhost:14100 in browser
  - Expected: Frontend UI loads with "Loading projects..." or project list

### 2. Database Initialization
- [ ] Verify database exists: `ls -la staging/.codeframe/state.db`
- [ ] Check database schema has latest columns:
  ```bash
  sqlite3 staging/.codeframe/state.db "PRAGMA table_info(tasks);" | grep parent_issue_number
  ```
  - Expected: Column exists with parent_issue_number field

---

## Phase 1: Agent Pool Manager (Task 4.3.1)

### Test 1.1: Agent Creation
- [ ] **Test**: Create multiple agent types
  ```python
  # In Python REPL or test script
  from codeframe.agents.agent_pool_manager import AgentPoolManager
  from codeframe.persistence.database import Database

  db = Database("staging/.codeframe/state.db")
  pool = AgentPoolManager(project_id=1, db=db, max_agents=10)

  # Create different agent types
  backend_id = pool.create_agent("backend")
  frontend_id = pool.create_agent("frontend")
  test_id = pool.create_agent("test")

  print(f"Created agents: {backend_id}, {frontend_id}, {test_id}")
  ```
- [ ] **Expected**: Agent IDs like `backend-worker-001`, `frontend-worker-002`, `test-worker-003`
- [ ] **Verify**: `pool.get_agent_status()` shows all 3 agents with status "idle"

### Test 1.2: Agent Pool Capacity Limit
- [ ] **Test**: Create agents until max capacity reached
  ```python
  # Try to create 11 agents (max is 10)
  try:
      for i in range(11):
          pool.create_agent("backend")
  except RuntimeError as e:
      print(f"✓ Capacity limit enforced: {e}")
  ```
- [ ] **Expected**: RuntimeError after 10th agent with message about maximum capacity

### Test 1.3: Agent Reuse
- [ ] **Test**: Verify idle agent reuse
  ```python
  # Get or create agent (should reuse idle one)
  agent_id = pool.get_or_create_agent("backend")
  status = pool.get_agent_status()
  print(f"Reused agent: {agent_id}")
  print(f"Total agents: {len(status)}")
  ```
- [ ] **Expected**: Returns existing backend agent ID, total count doesn't increase

### Test 1.4: Agent Status Transitions
- [ ] **Test**: Mark agent busy/idle/blocked
  ```python
  agent_id = pool.get_or_create_agent("backend")

  # Busy
  pool.mark_agent_busy(agent_id, task_id=1)
  assert pool.get_agent_status()[agent_id]["status"] == "busy"

  # Idle
  pool.mark_agent_idle(agent_id)
  assert pool.get_agent_status()[agent_id]["status"] == "idle"
  assert pool.get_agent_status()[agent_id]["tasks_completed"] == 1

  # Blocked
  pool.mark_agent_blocked(agent_id, blocked_by=[2, 3])
  assert pool.get_agent_status()[agent_id]["status"] == "blocked"
  ```
- [ ] **Expected**: All assertions pass, status transitions correctly

### Test 1.5: Agent Retirement
- [ ] **Test**: Retire agent and verify removal
  ```python
  initial_count = len(pool.get_agent_status())
  pool.retire_agent(agent_id)
  final_count = len(pool.get_agent_status())
  print(f"Agents before: {initial_count}, after: {final_count}")
  ```
- [ ] **Expected**: Agent count decreases by 1

---

## Phase 2: Dependency Resolver (Task 4.3.2)

### Test 2.1: Build Dependency Graph
- [ ] **Test**: Create tasks with dependencies
  ```python
  from codeframe.agents.dependency_resolver import DependencyResolver
  from codeframe.core.models import Task

  resolver = DependencyResolver()

  tasks = [
      Task(id=1, title="Setup DB", depends_on="", status="completed"),
      Task(id=2, title="Create models", depends_on="[1]", status="pending"),
      Task(id=3, title="Create API", depends_on="[2]", status="pending"),
      Task(id=4, title="Add tests", depends_on="[2,3]", status="pending"),
  ]

  resolver.build_dependency_graph(tasks)
  print(f"Graph built: {len(resolver.all_tasks)} tasks")
  ```
- [ ] **Expected**: Graph built successfully with 4 tasks
- [ ] **Verify**: No cycles detected

### Test 2.2: Get Ready Tasks
- [ ] **Test**: Find tasks ready for execution
  ```python
  ready = resolver.get_ready_tasks(exclude_completed=True)
  print(f"Ready tasks: {ready}")
  ```
- [ ] **Expected**: Returns `[2]` (task 1 is completed, so task 2 is unblocked)

### Test 2.3: Unblock Dependent Tasks
- [ ] **Test**: Complete task and find newly unblocked tasks
  ```python
  # Mark task 2 complete
  unblocked = resolver.unblock_dependent_tasks(completed_task_id=2)
  print(f"Newly unblocked: {unblocked}")
  ```
- [ ] **Expected**: Returns `[3]` (task 3 depends only on 2, task 4 still needs 3)

### Test 2.4: Cycle Detection
- [ ] **Test**: Detect circular dependencies
  ```python
  cycle_tasks = [
      Task(id=1, title="A", depends_on="[3]", status="pending"),
      Task(id=2, title="B", depends_on="[1]", status="pending"),
      Task(id=3, title="C", depends_on="[2]", status="pending"),
  ]

  try:
      resolver.build_dependency_graph(cycle_tasks)
      print("✗ FAILED: Should have detected cycle")
  except ValueError as e:
      print(f"✓ Cycle detected: {e}")
  ```
- [ ] **Expected**: ValueError with cycle description like `1 → 3 → 2 → 1`

### Test 2.5: Topological Sort
- [ ] **Test**: Get execution order
  ```python
  resolver.clear()
  resolver.build_dependency_graph(tasks)
  order = resolver.topological_sort()
  print(f"Execution order: {order}")
  ```
- [ ] **Expected**: Valid order like `[1, 2, 3, 4]` or `[1, 2, 3, 4]`

---

## Phase 3: Simple Agent Assignment (Task 4.3.3)

### Test 3.1: Frontend Task Assignment
- [ ] **Test**: Assign frontend-related tasks
  ```python
  from codeframe.agents.simple_assignment import SimpleAgentAssigner

  assigner = SimpleAgentAssigner()

  task = {"title": "Create login form component", "description": "Build React form"}
  agent_type = assigner.assign_agent_type(task)
  print(f"Assigned to: {agent_type}")
  ```
- [ ] **Expected**: `frontend-specialist`

### Test 3.2: Test Task Assignment
- [ ] **Test**: Assign test-related tasks
  ```python
  task = {"title": "Write integration tests", "description": "pytest coverage"}
  agent_type = assigner.assign_agent_type(task)
  print(f"Assigned to: {agent_type}")
  ```
- [ ] **Expected**: `test-engineer`

### Test 3.3: Backend Default Assignment
- [ ] **Test**: Default to backend for unclear tasks
  ```python
  task = {"title": "Fix the thing", "description": "Something broke"}
  agent_type = assigner.assign_agent_type(task)
  print(f"Assigned to: {agent_type}")
  ```
- [ ] **Expected**: `backend-worker`

### Test 3.4: Assignment Explanation
- [ ] **Test**: Get explanation for assignment
  ```python
  task = {"title": "Create API endpoint", "description": "REST API for users"}
  agent_type = assigner.assign_agent_type(task)
  explanation = assigner.get_assignment_explanation(task, agent_type)
  print(f"Explanation: {explanation}")
  ```
- [ ] **Expected**: Explanation mentions keywords like "api", "endpoint"

---

## Phase 4: LeadAgent Coordination (Task 4.3.4)

### Test 4.1: Parallel Execution Setup
- [ ] **Test**: Initialize LeadAgent with multi-agent support
  ```python
  from codeframe.agents.lead_agent import LeadAgent

  lead = LeadAgent(
      project_id=1,
      db=db,
      max_agents=5
  )

  print(f"Lead agent initialized with pool manager: {lead.agent_pool_manager is not None}")
  ```
- [ ] **Expected**: Agent pool manager, resolver, and assigner are initialized

### Test 4.2: End-to-End Multi-Agent Execution
- [ ] **Test**: Run full coordination cycle (async test)
  ```python
  import asyncio

  # Create test tasks in database
  db.create_task(Task(
      id=1, project_id=1, title="Setup environment",
      description="Initialize project", status="completed", depends_on=""
  ))
  db.create_task(Task(
      id=2, project_id=1, title="Create backend API",
      description="FastAPI endpoints", status="pending", depends_on="[1]"
  ))
  db.create_task(Task(
      id=3, project_id=1, title="Create frontend UI",
      description="React components", status="pending", depends_on="[1]"
  ))
  db.create_task(Task(
      id=4, project_id=1, title="Write tests",
      description="pytest and jest", status="pending", depends_on="[2,3]"
  ))

  # Run coordination
  results = asyncio.run(lead.start_multi_agent_execution(
      max_retries=3,
      max_concurrent=2
  ))

  print(f"Execution results: {results}")
  ```
- [ ] **Expected**:
  - Tasks 2 and 3 execute in parallel (both depend only on 1)
  - Task 4 waits for both 2 and 3 to complete
  - All tasks complete successfully or with clear error messages

---

## Phase 5: Integration Testing (Task 4.4)

### Test 5.1: Run Integration Test Suite
- [ ] **Command**: `source venv/bin/activate && pytest tests/test_multi_agent_integration.py -v`
- [ ] **Expected**: Tests pass (note: may need fixes for create_task signature)
- [ ] **Key test classes to verify**:
  - [ ] `TestAgentPoolBasics` - Pool operations
  - [ ] `TestDependencyResolution` - Dependency graph
  - [ ] `TestParallelExecution` - Parallel task handling
  - [ ] `TestErrorRecovery` - Retry logic

### Test 5.2: Check Test Coverage
- [ ] **Command**: `pytest tests/test_multi_agent_integration.py --cov=codeframe.agents --cov-report=term`
- [ ] **Expected**: Coverage report showing tested modules

---

## Phase 6: WebSocket Broadcasting (Bonus Feature)

### Test 6.1: Agent Creation Broadcast
- [ ] **Setup**: Connect WebSocket client to staging backend
- [ ] **Test**: Create agent and observe broadcast
- [ ] **Expected**: WebSocket message with agent_created event

### Test 6.2: Agent Retirement Broadcast
- [ ] **Test**: Retire agent and observe broadcast
- [ ] **Expected**: WebSocket message with agent_retired event

---

## Phase 7: Performance & Stress Testing

### Test 7.1: Maximum Concurrent Tasks
- [ ] **Test**: Execute 10 tasks concurrently with 5 max_concurrent limit
- [ ] **Expected**: Only 5 tasks execute at once, others wait

### Test 7.2: Large Dependency Graph
- [ ] **Test**: Create 50+ tasks with complex dependencies
- [ ] **Expected**: Graph builds successfully, no cycles detected

### Test 7.3: Agent Pool Exhaustion
- [ ] **Test**: Create more tasks than available agents
- [ ] **Expected**: Tasks queue and wait for agent availability

---

## Phase 8: Demo Scenarios

### Scenario 1: "Build a Feature" Demo
```python
# Demonstrate full workflow: planning → execution → testing
tasks = [
    Task(id=1, title="Design API schema", status="completed"),
    Task(id=2, title="Implement backend endpoints", depends_on="[1]"),
    Task(id=3, title="Create frontend forms", depends_on="[1]"),
    Task(id=4, title="Write API tests", depends_on="[2]"),
    Task(id=5, title="Write UI tests", depends_on="[3]"),
    Task(id=6, title="Integration testing", depends_on="[4,5]"),
]
```
- [ ] Show parallel execution of tasks 2 & 3
- [ ] Show tasks 4 & 5 waiting for 2 & 3
- [ ] Show task 6 waiting for all dependencies
- [ ] Display agent pool reuse throughout

### Scenario 2: "Error Recovery" Demo
- [ ] Inject a failing task
- [ ] Show retry logic (max 3 attempts)
- [ ] Show graceful failure handling
- [ ] Demonstrate continuation with other tasks

### Scenario 3: "Dependency Visualization" Demo
- [ ] Display dependency graph visually
- [ ] Highlight critical path
- [ ] Show parallel execution opportunities

---

## Post-Demo Cleanup

- [ ] Stop staging services: `pm2 stop all`
- [ ] Save logs: `pm2 logs --lines 1000 > /tmp/demo-logs.txt`
- [ ] Backup database: `cp staging/.codeframe/state.db staging/.codeframe/state.db.backup`
- [ ] Document any issues found during demo

---

## Quick Reference Commands

```bash
# Start/stop services
pm2 list
pm2 restart codeframe-staging-backend
pm2 restart codeframe-staging-frontend
pm2 logs codeframe-staging-backend --lines 50

# Database inspection
sqlite3 staging/.codeframe/state.db "SELECT * FROM tasks;"
sqlite3 staging/.codeframe/state.db "SELECT * FROM agents;"

# Health checks
curl http://localhost:14200/
curl http://localhost:14100/

# Run tests
pytest tests/test_multi_agent_integration.py -v -s
pytest tests/test_agent_pool_manager.py -v
pytest tests/test_dependency_resolver.py -v
```

---

## Notes

- All Python tests assume you're in the project root with virtualenv activated
- Database path: `staging/.codeframe/state.db`
- Frontend: http://localhost:14100
- Backend: http://localhost:14200
