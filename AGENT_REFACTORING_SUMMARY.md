# Agent Business Logic Refactoring Summary

## Overview
Updated agent architecture to support multi-agent per project pattern where agents are project-agnostic at creation time and derive project context from the tasks they execute.

## Architecture Changes

### Before
- Agents had `project_id` in constructor
- `agents` table had `project_id` column
- One-to-one relationship: agent → project

### After
- Agents are created without `project_id`
- `project_agents` junction table manages assignments
- Many-to-many relationship: agents ↔ projects
- Project context derived from `task.project_id`

## Files Modified

### 1. `/home/frankbria/projects/codeframe/codeframe/agents/worker_agent.py`

**Changes:**
- **Removed** `project_id` parameter from `__init__()`
- **Added** `_get_project_id()` helper method to extract project_id from current_task
- **Updated** all context management methods to use `_get_project_id()`:
  - `flash_save()`: Gets project_id from current task
  - `should_flash_save()`: Gets project_id from current task
  - `save_context_item()`: Gets project_id from current task
  - `load_context()`: Gets project_id from current task
  - `update_tiers()`: Gets project_id from current task
  - `complete_task()`: Sets current_task first, then uses `_get_project_id()`
  - `_create_quality_blocker()`: Gets project_id from task parameter

**Breaking Changes:**
- Agents can no longer be initialized with project_id
- All context operations require a task to be assigned first
- Use `Database.assign_agent_to_project()` for explicit assignment

**Migration Path:**
```python
# Old way
agent = WorkerAgent(agent_id="backend-001", agent_type="backend",
                    provider="anthropic", project_id=123, db=db)
await agent.save_context_item(ContextItemType.CODE, "code here")

# New way
agent = WorkerAgent(agent_id="backend-001", agent_type="backend",
                    provider="anthropic", db=db)
# Assign to project
db.assign_agent_to_project(project_id=123, agent_id="backend-001", role="worker")
# Execute task (establishes project context)
agent.execute_task(task)  # task.project_id = 123
# Now context operations work
await agent.save_context_item(ContextItemType.CODE, "code here")
```

### 2. `/home/frankbria/projects/codeframe/codeframe/agents/lead_agent.py`

**Changes:**
- **No changes needed** - LeadAgent correctly keeps project_id as it orchestrates project-level work
- LeadAgent still initializes with `project_id` parameter
- All project-scoped operations remain unchanged

### 3. `/home/frankbria/projects/codeframe/codeframe/agents/agent_pool_manager.py`

**Status:** NEEDS UPDATE

**Required Changes:**
- Update `_create_hybrid_agent()` to remove project_id parameter when creating HybridWorkerAgent
- Update `_create_traditional_agent()` to remove project_id parameter for:
  - BackendWorkerAgent
  - ReviewWorkerAgent
- Keep project_id tracked in pool manager for assignment purposes
- Add agent-to-project assignment after creation

### 4. `/home/frankbria/projects/codeframe/codeframe/agents/backend_worker_agent.py`

**Status:** NEEDS UPDATE

**Required Changes:**
- Remove `project_id` parameter from `__init__()`
- Update all method calls that assume `self.project_id` exists
- Use `_get_project_id()` inherited from WorkerAgent base class

### 5. `/home/frankbria/projects/codeframe/codeframe/agents/frontend_worker_agent.py`

**Status:** NEEDS UPDATE (minor)

**Required Changes:**
- Already has `project_id` as optional parameter
- Remove default `project_id` parameter completely
- Update any direct usage of `self.project_id`

### 6. `/home/frankbria/projects/codeframe/codeframe/agents/test_worker_agent.py`

**Status:** NEEDS UPDATE

**Required Changes:**
- Remove `project_id` parameter from `__init__()`
- Update any method calls that assume `self.project_id` exists

### 7. `/home/frankbria/projects/codeframe/codeframe/agents/review_worker_agent.py`

**Status:** NEEDS UPDATE

**Required Changes:**
- Remove `project_id` parameter from `__init__()`
- Update constructor call to parent WorkerAgent
- Update any direct usage of `self.project_id`

### 8. `/home/frankbria/projects/codeframe/codeframe/agents/hybrid_worker.py`

**Status:** NEEDS UPDATE

**Required Changes:**
- Remove `project_id` parameter from `__init__()`
- Update constructor call to parent WorkerAgent
- Update any direct usage of `self.project_id`
- Update context management methods if any

## How Agents Get Project Context Now

### Flow:
1. **Agent Creation**: Agent created without project_id
   ```python
   agent = WorkerAgent(agent_id="backend-001", agent_type="backend",
                       provider="anthropic", db=db)
   ```

2. **Project Assignment** (optional, for tracking):
   ```python
   db.assign_agent_to_project(project_id=123, agent_id="backend-001", role="worker")
   ```

3. **Task Assignment**: Task with project_id assigned to agent
   ```python
   task = Task(id=1, project_id=123, title="Implement API", ...)
   agent.execute_task(task)  # Sets agent.current_task
   ```

4. **Context Operations**: Use `_get_project_id()` to extract from current_task
   ```python
   # Inside WorkerAgent methods:
   project_id = self._get_project_id()  # Returns 123 from current_task
   ```

### Key Points:
- **Agents are reusable**: Same agent can work on multiple projects
- **Dynamic context**: Project context switches when new task assigned
- **Error handling**: Operations fail gracefully if no task assigned:
  ```python
  ValueError: No task currently assigned. Project context is derived from active task.
  ```

## Test Recommendations

### Unit Tests
1. Test agent initialization without project_id
2. Test `_get_project_id()` with and without current_task
3. Test context operations throw error when no task assigned
4. Test context operations work after task assignment
5. Test agent can switch between projects

### Integration Tests
1. Test multi-agent coordination with dynamic project assignment
2. Test agent pool manager creates agents correctly
3. Test LeadAgent orchestration with new agent pattern
4. Test Database.assign_agent_to_project() and get_agents_for_project()

### Migration Tests
1. Test existing code paths still work
2. Test backwards compatibility where needed
3. Test error messages are helpful

## Rollout Plan

### Phase 1: Core WorkerAgent ✅ COMPLETE
- Update WorkerAgent base class
- Add _get_project_id() helper
- Update all context methods

### Phase 2: Specialized Agents (NEXT)
- Update BackendWorkerAgent
- Update FrontendWorkerAgent
- Update TestWorkerAgent
- Update ReviewWorkerAgent
- Update HybridWorkerAgent

### Phase 3: Agent Pool Manager (NEXT)
- Update _create_hybrid_agent()
- Update _create_traditional_agent()
- Add project assignment logic

### Phase 4: Testing
- Run existing test suite
- Fix failing tests
- Add new test coverage

### Phase 5: Documentation
- Update API docs
- Update architecture diagrams
- Update migration guide

## Success Criteria

✅ WorkerAgent base class updated
⬜ All specialized agent classes updated
⬜ AgentPoolManager updated
⬜ All tests passing
⬜ No breaking changes to LeadAgent
⬜ Database integration verified
⬜ Documentation updated

## Notes

- LeadAgent is intentionally NOT changed - it remains project-scoped
- AgentPoolManager needs project_id to assign agents to projects
- Context operations require an active task
- This enables true multi-tenancy at agent level
