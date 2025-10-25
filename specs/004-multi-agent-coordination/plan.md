# Sprint 4 Implementation Plan: Multi-Agent Coordination

## Tech Stack

### Backend
- **Language**: Python 3.11+
- **Concurrency**: asyncio for parallel agent execution
- **Database**: SQLite with existing schema
- **Agent Framework**: Existing WorkerAgent base class
- **Assignment**: simple_assignment.py (keyword-based routing)
- **Real-time**: WebSocket broadcasts (cf-45 infrastructure)

### Frontend
- **Framework**: React 18 + TypeScript
- **UI Library**: Tailwind CSS
- **State Management**: React hooks (useState, useEffect)
- **Real-time**: WebSocket client (existing)

### Testing
- **Framework**: pytest
- **Coverage**: pytest-cov
- **Async Testing**: pytest-asyncio
- **Mocking**: unittest.mock

## Architecture Overview

### Agent Hierarchy

```
LeadAgent (Coordinator)
├── Agent Pool Management
│   ├── create_agent(agent_type) → agent_id
│   ├── get_available_agent(agent_type) → agent_id
│   └── retire_agent(agent_id)
├── Task Assignment
│   ├── assign_task(task) → agent_id
│   └── Uses simple_assignment.py for routing
└── Dependency Resolution
    ├── build_dependency_graph(tasks)
    ├── get_ready_tasks() → [tasks]
    └── unblock_dependent_tasks(completed_task_id)

WorkerAgent (Base Class - Existing)
├── BackendWorkerAgent (Sprint 3 - Existing)
│   ├── Python/FastAPI code generation
│   ├── Database operations
│   └── Test-driven development
├── FrontendWorkerAgent (NEW - cf-21)
│   ├── React/TypeScript code generation
│   ├── Component creation
│   └── UI testing integration
└── TestWorkerAgent (NEW - cf-22)
    ├── Unit test generation (pytest)
    ├── Integration test creation
    └── Test execution and reporting
```

### Task Dependency System

```python
# Database Schema Enhancement
tasks table:
  - id (existing)
  - title (existing)
  - description (existing)
  - assigned_to (existing)
  - status (existing)
  - depends_on: JSON array of task IDs ["task_1", "task_3"]
  - blocked_by: JSON array of task IDs (computed)

# Dependency Resolution Flow
1. LeadAgent.build_dependency_graph(tasks)
   → Creates DAG, validates no cycles
2. LeadAgent.get_ready_tasks()
   → Returns tasks with all dependencies completed
3. Worker completes task
   → Broadcasts completion
4. LeadAgent.unblock_dependent_tasks(task_id)
   → Updates blocked_by for dependent tasks
   → Assigns newly unblocked tasks
```

### Agent Pool Management

```python
# Agent Pool Structure
agent_pool = {
    "backend-worker-001": {
        "instance": BackendWorkerAgent(...),
        "status": "busy",  # idle | busy | blocked
        "current_task": "task_5",
        "agent_type": "backend-worker"
    },
    "frontend-specialist-001": {
        "instance": FrontendWorkerAgent(...),
        "status": "idle",
        "current_task": None,
        "agent_type": "frontend-specialist"
    }
}

# Agent Lifecycle
1. Task assigned → check pool for idle agent of type
2. No idle agent → create new agent (up to max_agents limit)
3. Agent completes task → mark idle, ready for next task
4. Agent errors → retry with different agent, mark failed agent
5. Session end → all agents retire gracefully
```

## File Structure

### New Files to Create

```
codeframe/agents/
├── frontend_worker_agent.py       # cf-21: Frontend agent
├── test_worker_agent.py           # cf-22: Test agent
├── dependency_resolver.py         # cf-23: DAG + dependency logic
└── agent_pool_manager.py          # cf-24: Pool management

codeframe/ui/
└── websocket_broadcasts.py        # Enhancement: New message types

tests/
├── test_frontend_worker_agent.py  # cf-21 tests
├── test_test_worker_agent.py      # cf-22 tests
├── test_dependency_resolver.py    # cf-23 tests
├── test_agent_pool_manager.py     # cf-24 tests
└── test_multi_agent_integration.py # End-to-end integration

web-ui/src/components/
└── Dashboard.tsx                  # Enhancement: Multi-agent view
```

### Files to Modify

```
codeframe/agents/
├── lead_agent.py                  # Add pool management, dependency resolution
└── __init__.py                    # Export new agent classes

codeframe/persistence/
└── database.py                    # Add depends_on column to tasks

web-ui/src/types/
└── index.ts                       # Add new agent types, message types
```

## Implementation Phases

### Phase 1: Frontend Worker Agent (cf-21)
**Duration**: 3-4 hours
**Priority**: P0

**Implementation**:
```python
# codeframe/agents/frontend_worker_agent.py

class FrontendWorkerAgent(WorkerAgent):
    """React/TypeScript code generation agent"""

    def __init__(self, agent_id, llm_provider, project_id, db, ws_manager=None):
        super().__init__(agent_id, llm_provider, project_id, db, ws_manager)
        self.agent_type = "frontend-specialist"

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute frontend task with React/TypeScript generation"""
        # 1. Analyze task requirements
        # 2. Generate React component code
        # 3. Create TypeScript types
        # 4. Write component file
        # 5. Generate component tests (optional)
        # 6. Update imports/exports
        # 7. Broadcast completion

    def _generate_react_component(self, spec: Dict) -> str:
        """Generate React component code from specification"""
        # Use Claude API to generate component
        # Follow project conventions (Tailwind, TypeScript, etc.)

    def _generate_typescript_types(self, spec: Dict) -> str:
        """Generate TypeScript interfaces/types"""
```

**Tests** (16 tests):
- Component generation (basic, with props, with state)
- TypeScript type generation
- File creation in correct location
- Import/export updates
- Error handling (invalid specs, file conflicts)
- Integration with WebSocket broadcasts

**Files**:
- `codeframe/agents/frontend_worker_agent.py` (~400 lines)
- `tests/test_frontend_worker_agent.py` (~600 lines)

---

### Phase 2: Test Worker Agent (cf-22)
**Duration**: 3-4 hours
**Priority**: P0

**Implementation**:
```python
# codeframe/agents/test_worker_agent.py

class TestWorkerAgent(WorkerAgent):
    """Unit and integration test generation agent"""

    def __init__(self, agent_id, llm_provider, project_id, db, ws_manager=None):
        super().__init__(agent_id, llm_provider, project_id, db, ws_manager)
        self.agent_type = "test-engineer"

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute test creation task"""
        # 1. Analyze code to test
        # 2. Generate pytest test cases
        # 3. Write test file
        # 4. Run tests to validate
        # 5. Fix failing tests (up to 3 attempts)
        # 6. Broadcast results

    def _generate_pytest_tests(self, target_file: str, spec: Dict) -> str:
        """Generate pytest test cases for target code"""
        # Use Claude API to generate tests
        # Follow pytest conventions
        # Include fixtures, parametrize, mocks

    def _analyze_target_code(self, file_path: str) -> Dict:
        """Analyze code to understand test requirements"""
        # Read target file
        # Extract functions, classes, methods
        # Identify edge cases and scenarios
```

**Tests** (14 tests):
- Test generation (functions, classes, async code)
- Test file creation in correct location
- Test execution and validation
- Self-correction on test failures
- Integration with pytest runner
- WebSocket broadcast integration

**Files**:
- `codeframe/agents/test_worker_agent.py` (~350 lines)
- `tests/test_test_worker_agent.py` (~550 lines)

---

### Phase 3: Task Dependency Resolution (cf-23)
**Duration**: 4-5 hours
**Priority**: P0

**Implementation**:
```python
# codeframe/agents/dependency_resolver.py

class DependencyResolver:
    """DAG-based task dependency resolution"""

    def __init__(self, db):
        self.db = db
        self.dependency_graph = {}  # {task_id: [dependent_task_ids]}

    def build_dependency_graph(self, tasks: List[Dict]) -> None:
        """Build DAG from task dependencies"""
        # 1. Parse depends_on from each task
        # 2. Create adjacency list
        # 3. Validate no cycles (topological sort)
        # 4. Raise exception if cycles detected

    def get_ready_tasks(self) -> List[Dict]:
        """Get tasks with all dependencies completed"""
        # 1. Query tasks with status='pending'
        # 2. For each task, check depends_on tasks
        # 3. Return tasks where all dependencies are 'completed'

    def unblock_dependent_tasks(self, completed_task_id: str) -> List[str]:
        """Find tasks unblocked by completing this task"""
        # 1. Find all tasks that depend on completed_task_id
        # 2. Check if other dependencies also complete
        # 3. Return list of newly unblocked task IDs

    def detect_cycles(self) -> List[List[str]]:
        """Detect circular dependencies using DFS"""
        # Depth-first search with cycle detection
        # Return list of cycles found

    def validate_dependencies(self, task_id: str, depends_on: List[str]) -> bool:
        """Validate dependencies don't create cycles"""
        # Temporarily add edge, check for cycles
        # Remove edge if cycle detected
```

**Database Migration**:
```python
# Add to codeframe/persistence/database.py

def _initialize_schema(self):
    # Existing tables...

    # Add depends_on column to tasks table
    self.execute("""
        ALTER TABLE tasks
        ADD COLUMN depends_on TEXT DEFAULT '[]'
    """)

    # Create task_dependencies table for complex queries
    self.execute("""
        CREATE TABLE IF NOT EXISTS task_dependencies (
            id INTEGER PRIMARY KEY,
            task_id TEXT NOT NULL,
            depends_on_task_id TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id),
            FOREIGN KEY (depends_on_task_id) REFERENCES tasks(id),
            UNIQUE(task_id, depends_on_task_id)
        )
    """)
```

**Tests** (18 tests):
- DAG construction (simple, complex graphs)
- Cycle detection (direct, indirect cycles)
- Ready task identification
- Unblocking logic
- Database integration
- Edge cases (self-dependency, missing tasks)

**Files**:
- `codeframe/agents/dependency_resolver.py` (~300 lines)
- `tests/test_dependency_resolver.py` (~700 lines)
- `codeframe/persistence/database.py` (modify ~50 lines)

---

### Phase 4: Parallel Agent Execution (cf-24)
**Duration**: 5-6 hours
**Priority**: P0

**Implementation**:
```python
# codeframe/agents/agent_pool_manager.py

class AgentPoolManager:
    """Manage pool of worker agents for parallel execution"""

    def __init__(self, project_id, db, ws_manager, max_agents=10):
        self.project_id = project_id
        self.db = db
        self.ws_manager = ws_manager
        self.max_agents = max_agents
        self.agent_pool = {}  # {agent_id: agent_info}
        self.next_agent_number = 1
        self.factory = AgentFactory()

    def get_or_create_agent(self, agent_type: str) -> str:
        """Get idle agent or create new one"""
        # 1. Check for idle agent of this type
        # 2. If found, return agent_id
        # 3. If not found and under limit, create new agent
        # 4. If at limit, wait for agent to become available
        # 5. Return agent_id

    def create_agent(self, agent_type: str) -> str:
        """Create new agent instance"""
        # 1. Generate agent_id
        # 2. Use AgentFactory to create agent
        # 3. Add to pool
        # 4. Broadcast agent created
        # 5. Return agent_id

    def mark_agent_busy(self, agent_id: str, task_id: str) -> None:
        """Mark agent as busy with task"""

    def mark_agent_idle(self, agent_id: str) -> None:
        """Mark agent as idle and ready"""

    def retire_agent(self, agent_id: str) -> None:
        """Remove agent from pool"""

    def get_agent_status(self) -> Dict[str, Dict]:
        """Get status of all agents in pool"""


# Enhancement to codeframe/agents/lead_agent.py

class LeadAgent:
    def __init__(self, project_id, db, ws_manager=None):
        # Existing initialization...
        self.pool_manager = AgentPoolManager(project_id, db, ws_manager)
        self.dependency_resolver = DependencyResolver(db)
        self.assignment_running = False

    async def start_multi_agent_execution(self) -> None:
        """Start parallel task execution loop"""
        self.assignment_running = True

        while self.assignment_running:
            # 1. Get ready tasks (dependencies satisfied)
            ready_tasks = self.dependency_resolver.get_ready_tasks()

            # 2. For each ready task
            for task in ready_tasks:
                # Assign to agent (non-blocking)
                asyncio.create_task(self._assign_and_execute_task(task))

            # 3. Wait before next check
            await asyncio.sleep(1)

            # 4. Check if all tasks complete
            if self._all_tasks_complete():
                self.assignment_running = False

    async def _assign_and_execute_task(self, task: Dict) -> None:
        """Assign task to agent and execute in background"""
        # 1. Determine agent type
        agent_type = assign_task_to_agent(task)

        # 2. Get or create agent
        agent_id = self.pool_manager.get_or_create_agent(agent_type)

        # 3. Update database
        self.db.execute(
            "UPDATE tasks SET assigned_to = ?, status = 'in_progress' WHERE id = ?",
            (agent_id, task["id"])
        )

        # 4. Get agent instance
        agent_info = self.pool_manager.agent_pool[agent_id]
        agent = agent_info["instance"]

        # 5. Mark agent busy
        self.pool_manager.mark_agent_busy(agent_id, task["id"])

        # 6. Execute task (async)
        try:
            result = await agent.execute_task(task)

            # 7. Mark task complete
            self.db.execute(
                "UPDATE tasks SET status = 'completed' WHERE id = ?",
                (task["id"],)
            )

            # 8. Unblock dependent tasks
            unblocked = self.dependency_resolver.unblock_dependent_tasks(task["id"])

        except Exception as e:
            # Handle task failure
            self.db.execute(
                "UPDATE tasks SET status = 'failed' WHERE id = ?",
                (task["id"],)
            )

        finally:
            # 9. Mark agent idle
            self.pool_manager.mark_agent_idle(agent_id)
```

**WebSocket Enhancements**:
```python
# Add to codeframe/ui/websocket_broadcasts.py

async def broadcast_agent_created(agent_id: str, agent_type: str):
    """Broadcast new agent creation"""

async def broadcast_agent_retired(agent_id: str):
    """Broadcast agent retirement"""

async def broadcast_task_assigned(task_id: str, agent_id: str):
    """Broadcast task assignment to agent"""

async def broadcast_task_blocked(task_id: str, blocked_by: List[str]):
    """Broadcast task blocked by dependencies"""

async def broadcast_task_unblocked(task_id: str):
    """Broadcast task unblocked"""
```

**Tests** (22 tests):
- Agent pool creation and management
- Parallel task execution (2, 3, 5 agents)
- Agent reuse (idle agents assigned new tasks)
- Max agent limit enforcement
- Task assignment integration
- Dependency-based execution order
- Error handling (agent crashes, task failures)
- Integration tests (end-to-end multi-agent scenarios)

**Files**:
- `codeframe/agents/agent_pool_manager.py` (~400 lines)
- `codeframe/agents/lead_agent.py` (modify ~200 lines)
- `codeframe/ui/websocket_broadcasts.py` (add ~100 lines)
- `tests/test_agent_pool_manager.py` (~800 lines)
- `tests/test_multi_agent_integration.py` (~600 lines)

---

### Phase 5: Dashboard Multi-Agent View (cf-24 UI)
**Duration**: 3-4 hours
**Priority**: P0

**Implementation**:
```typescript
// web-ui/src/components/Dashboard.tsx

interface Agent {
  id: string;
  type: string;
  status: 'idle' | 'busy' | 'blocked';
  currentTask: string | null;
  tasksCompleted: number;
}

interface DashboardState {
  agents: Agent[];
  tasks: Task[];
  activityFeed: ActivityItem[];
  progress: { completed: number; total: number };
}

export default function Dashboard() {
  const [agents, setAgents] = useState<Agent[]>([]);

  // WebSocket message handler
  useEffect(() => {
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);

      switch (message.type) {
        case 'agent_created':
          setAgents(prev => [...prev, message.agent]);
          break;

        case 'agent_status_changed':
          setAgents(prev => prev.map(a =>
            a.id === message.agent_id
              ? { ...a, status: message.status, currentTask: message.task_id }
              : a
          ));
          break;

        case 'task_assigned':
          // Update task and agent state
          break;

        case 'task_blocked':
          // Show blocked indicator
          break;

        // ... other message types
      }
    };
  }, []);

  return (
    <div className="dashboard">
      {/* Agent Status Section */}
      <section className="agents-section">
        <h2>Active Agents ({agents.length})</h2>
        <div className="agent-grid">
          {agents.map(agent => (
            <AgentCard key={agent.id} agent={agent} />
          ))}
        </div>
      </section>

      {/* Task Board with Dependencies */}
      <section className="tasks-section">
        <TaskBoard tasks={tasks} />
      </section>

      {/* Activity Feed */}
      <section className="activity-section">
        <ActivityFeed items={activityFeed} />
      </section>
    </div>
  );
}
```

**UI Components**:
- AgentCard: Shows agent status, current task, completion count
- TaskBoard: Kanban-style board with dependency visualization
- DependencyGraph: Visual representation of task dependencies
- ActivityFeed: Real-time updates (existing, enhanced)

**Files**:
- `web-ui/src/components/Dashboard.tsx` (modify ~300 lines)
- `web-ui/src/components/AgentCard.tsx` (new, ~150 lines)
- `web-ui/src/components/TaskBoard.tsx` (modify ~200 lines)
- `web-ui/src/types/index.ts` (add Agent types)

---

### Phase 6: Integration Testing & Validation
**Duration**: 2-3 hours
**Priority**: P0

**End-to-End Test Scenarios**:
```python
# tests/test_multi_agent_integration.py

async def test_three_agent_parallel_execution():
    """Test 3 agents working on independent tasks"""
    # 1. Create 3 tasks (backend, frontend, test)
    # 2. Start multi-agent execution
    # 3. Verify all 3 agents created
    # 4. Verify tasks execute in parallel
    # 5. Verify all tasks complete successfully

async def test_dependency_blocking_and_unblocking():
    """Test task waits for dependency, then executes"""
    # 1. Create task A (no dependencies)
    # 2. Create task B (depends on A)
    # 3. Start execution
    # 4. Verify task B remains pending
    # 5. Complete task A
    # 6. Verify task B auto-starts
    # 7. Verify task B completes

async def test_complex_dependency_graph():
    """Test 10 tasks with complex dependencies"""
    # 1. Create DAG with 10 tasks
    # 2. Verify correct execution order
    # 3. Verify parallel execution where possible
    # 4. Verify all tasks complete

async def test_agent_reuse_and_retirement():
    """Test agent pool efficiency"""
    # 1. Execute 5 backend tasks sequentially
    # 2. Verify only 1 backend agent created
    # 3. Verify agent reused for all 5 tasks
    # 4. Verify agent retired after completion
```

---

## Advanced Features (P1 - Optional)

### cf-24.5: Subagent Spawning
**Duration**: 3-4 hours
**Status**: Optional for Sprint 4

**Concept**: Worker agents can spawn specialist subagents for specific tasks (code review, accessibility checks, security scanning)

**Implementation Approach**:
- Add `spawn_subagent(subagent_type, task)` to WorkerAgent
- Subagents report to parent agent
- Parent aggregates results
- Hierarchical WebSocket updates

**Defer to**: Sprint 8 (Review & Polish) or later

---

### cf-24.6: Claude Code Skills Integration
**Duration**: 3-4 hours
**Status**: Optional for Sprint 4

**Concept**: Integrate with Superpowers framework to use skills like TDD, debugging, refactoring

**Implementation Approach**:
- Detect available skills in agent environment
- Invoke skills via Skill tool
- Track skill usage and results
- Report skill invocations in activity feed

**Defer to**: Sprint 7 (Agent Maturity) or later

---

### cf-25: Bottleneck Detection
**Duration**: 2-3 hours
**Status**: Optional for Sprint 4

**Concept**: Identify when multiple tasks wait on single dependency, highlight in UI

**Implementation Approach**:
```python
class BottleneckDetector:
    def detect_bottlenecks(self, tasks: List[Dict]) -> List[Dict]:
        """Find tasks blocking multiple other tasks"""
        bottlenecks = []

        for task in tasks:
            if task["status"] != "completed":
                # Count how many tasks depend on this one
                dependent_count = len([
                    t for t in tasks
                    if task["id"] in t.get("depends_on", [])
                ])

                if dependent_count >= 3:  # Threshold
                    bottlenecks.append({
                        "task_id": task["id"],
                        "blocked_count": dependent_count,
                        "severity": "high" if dependent_count >= 5 else "medium"
                    })

        return bottlenecks
```

**Defer to**: Post-Sprint 4 polish or Sprint 5

---

## Migration Strategy

### Database Migration

**Before Sprint 4**:
```sql
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    title TEXT,
    description TEXT,
    assigned_to TEXT,
    status TEXT
);
```

**After Sprint 4**:
```sql
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    title TEXT,
    description TEXT,
    assigned_to TEXT,
    status TEXT,
    depends_on TEXT DEFAULT '[]'  -- JSON array of task IDs
);

CREATE TABLE task_dependencies (
    id INTEGER PRIMARY KEY,
    task_id TEXT NOT NULL,
    depends_on_task_id TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id),
    FOREIGN KEY (depends_on_task_id) REFERENCES tasks(id),
    UNIQUE(task_id, depends_on_task_id)
);
```

**Migration Script**:
```python
def migrate_sprint4():
    """Add dependency tracking to existing database"""
    db = Database()

    # Add depends_on column to tasks
    db.execute("ALTER TABLE tasks ADD COLUMN depends_on TEXT DEFAULT '[]'")

    # Create task_dependencies table
    db.execute("""
        CREATE TABLE IF NOT EXISTS task_dependencies (
            id INTEGER PRIMARY KEY,
            task_id TEXT NOT NULL,
            depends_on_task_id TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id),
            FOREIGN KEY (depends_on_task_id) REFERENCES tasks(id),
            UNIQUE(task_id, depends_on_task_id)
        )
    """)

    db.commit()
```

### Backward Compatibility

**Existing Sprint 3 Code**:
- BackendWorkerAgent continues working unchanged
- LeadAgent can still assign tasks individually
- WebSocket infrastructure remains compatible

**New Sprint 4 Code**:
- Optional: Use `start_multi_agent_execution()` for parallel mode
- Fallback: Continue using single-agent mode if needed
- Graceful: Tasks without `depends_on` work as before

---

## Testing Strategy

### Unit Tests (70+ tests)
- Frontend agent: 16 tests
- Test agent: 14 tests
- Dependency resolver: 18 tests
- Agent pool manager: 22 tests

### Integration Tests (15+ tests)
- Multi-agent parallel execution
- Dependency blocking/unblocking
- Complex dependency graphs
- Agent reuse and retirement
- WebSocket integration
- Dashboard updates

### Manual Testing Checklist
- [ ] Create project with 10 tasks (3 backend, 3 frontend, 3 test, 1 integration)
- [ ] Set up dependencies: frontend depends on backend, integration depends on all
- [ ] Start multi-agent execution
- [ ] Verify agents created dynamically
- [ ] Verify parallel execution (backend, frontend, test run simultaneously)
- [ ] Verify dependency blocking (frontend waits for backend)
- [ ] Verify unblocking (frontend starts after backend completes)
- [ ] Verify dashboard updates in real-time
- [ ] Verify activity feed shows all events
- [ ] Verify progress bar updates correctly
- [ ] Verify all tasks complete successfully

---

## Performance Targets

- **Agent Creation**: < 100ms per agent
- **Task Assignment**: < 100ms per task
- **Dependency Resolution**: < 50ms per check
- **Parallel Execution**: 3-5 agents without degradation
- **WebSocket Latency**: < 500ms from event to UI update
- **Dashboard Rendering**: < 100ms for agent list updates

---

## Risk Mitigation

### Race Conditions
**Risk**: Multiple agents updating same database rows
**Mitigation**:
- Use database transactions
- Row-level locking with `BEGIN IMMEDIATE`
- Retry logic on deadlock

### Deadlocks
**Risk**: Circular task dependencies
**Mitigation**:
- Validate dependencies on task creation
- Detect cycles in DAG before execution
- Reject cyclic dependencies early

### Resource Exhaustion
**Risk**: Too many agents spawned
**Mitigation**:
- Max agent limit (default: 10)
- Agent retirement after idle timeout
- Pool size monitoring

### Agent Failures
**Risk**: Agent crashes mid-task
**Mitigation**:
- Try-except around agent execution
- Retry failed tasks (max 3 attempts)
- Graceful degradation (mark task failed, continue)

---

## Success Criteria

### Functional
- ✅ 3 agent types implemented (Backend, Frontend, Test)
- ✅ Agents execute tasks in parallel
- ✅ Task dependencies respected
- ✅ Dashboard shows all agents and tasks
- ✅ Real-time updates via WebSocket

### Quality
- ✅ ≥85% test coverage for new code
- ✅ 0 regressions (all Sprint 3 tests pass)
- ✅ 0 race conditions in integration tests
- ✅ 0 deadlocks in dependency resolution

### Performance
- ✅ 3-5 concurrent agents supported
- ✅ Task assignment < 100ms
- ✅ Dependency resolution < 50ms
- ✅ Dashboard updates < 500ms

---

## Rollout Plan

### Day 1-2: Core Agents (cf-21, cf-22)
- Implement FrontendWorkerAgent
- Implement TestWorkerAgent
- Write comprehensive tests
- Validate against existing BackendWorkerAgent

### Day 3: Dependency Resolution (cf-23)
- Implement DependencyResolver
- Add database schema changes
- Write DAG and cycle detection tests
- Validate with complex dependency graphs

### Day 4-5: Parallel Execution (cf-24)
- Implement AgentPoolManager
- Enhance LeadAgent with multi-agent loop
- Add WebSocket broadcast enhancements
- Write integration tests

### Day 6: Dashboard UI (cf-24 UI)
- Add agent status display
- Add dependency visualization
- Update activity feed
- Manual testing

### Day 7: Integration & Polish
- End-to-end testing
- Performance profiling
- Bug fixes
- Documentation

---

## Documentation Requirements

### Developer Documentation
- API documentation for new classes
- Usage examples for multi-agent execution
- Dependency configuration guide
- Agent pool management guide

### User Documentation
- Dashboard guide (multi-agent view)
- Task dependency tutorial
- Troubleshooting guide (blocked tasks, agent failures)

### Internal Documentation
- Architecture decision records
- Performance benchmarks
- Test coverage reports
- Sprint review notes

---

## Dependencies

### External
- No new external dependencies required
- Uses existing: anthropic, websockets, pytest, asyncio

### Internal
- Sprint 3 complete: BackendWorkerAgent, WebSocket infrastructure
- simple_assignment.py (from Sprint 3 conclusion)
- AgentFactory (from agent refactor)
- Database schema (existing)

---

## Post-Sprint 4 Roadmap

### Sprint 5: Human in the Loop
- Blocker system (agents ask questions)
- SYNC vs ASYNC blockers
- Notification system

### Sprint 6: Context Management
- Virtual Project system
- Flash saves before compaction
- Context tiering (HOT/WARM/COLD)

### Sprint 7: Agent Maturity
- Performance metrics tracking
- Maturity levels (D1-D4)
- Adaptive task instructions

### Sprint 8: Review & Polish
- Review Agent implementation
- Quality gates
- Checkpoint/recovery system
- MVP completion

### Sprint 9: Advanced Agent Routing
- Capability-based matching
- Project-level agent definitions
- Task analysis and scoring
- Sophisticated agent selection
