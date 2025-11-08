# Research: Multi-Agent Coordination Patterns

**Sprint**: 4 | **Date**: October 2025
**Phase**: Research & Design Decisions
**Context**: Implementing parallel agent execution with dependency resolution

---

## Executive Summary

This document consolidates research findings and design decisions for implementing multi-agent coordination in CodeFRAME. The implementation supports up to 10 concurrent worker agents (Backend, Frontend, Test) with DAG-based dependency resolution, centralized state management, and real-time WebSocket coordination.

Key decisions:
- **Agent Pool Pattern** with configurable max concurrency (default: 10)
- **DAG-based dependency resolution** with cycle detection
- **React Context + useReducer** for frontend state management
- **WebSocket broadcasts** for multi-agent lifecycle coordination
- **Threading with RLock** for thread-safe pool operations (later migrated to async in Sprint 5)

---

## 1. Agent Pool Pattern

### Decision: Pool-Based Agent Reuse with Max Concurrency

**Rationale**:
- Creating new agent instances is expensive (LLM client initialization, resource allocation)
- Unbounded agent creation can exhaust system resources (memory, API rate limits)
- Agent reuse amortizes initialization cost across multiple tasks
- Fixed pool size provides predictable resource consumption

**Implementation**:
```python
class AgentPoolManager:
    def __init__(self, project_id, db, ws_manager, max_agents=10):
        self.agent_pool: Dict[str, Dict[str, Any]] = {}
        self.max_agents = max_agents
        self.lock = RLock()  # Thread-safe pool operations

    def get_or_create_agent(self, agent_type: str) -> str:
        with self.lock:
            # 1. Look for idle agent of this type
            for agent_id, agent_info in self.agent_pool.items():
                if (agent_info["agent_type"] == agent_type and
                    agent_info["status"] == "idle"):
                    return agent_id

            # 2. No idle agent - create new one if under limit
            if len(self.agent_pool) >= self.max_agents:
                raise RuntimeError(f"Agent pool at maximum capacity ({self.max_agents})")

            return self.create_agent(agent_type)
```

**Agent Lifecycle States**:
- **idle**: Agent ready to accept new task
- **busy**: Agent executing task
- **blocked**: Agent waiting on dependencies

**Pool Metadata Per Agent**:
```python
{
    "instance": BackendWorkerAgent(...),
    "status": "idle",              # idle | busy | blocked
    "current_task": None,          # Task ID or None
    "agent_type": "backend",       # backend | frontend | test
    "tasks_completed": 0,          # Completion counter
    "blocked_by": None            # List of blocking task IDs
}
```

### Resource Exhaustion Prevention

**Max Concurrency Limit**: Default 10 agents
- Prevents unbounded resource consumption
- Enforced at pool creation time
- Raises `RuntimeError` when limit exceeded
- Configurable per deployment (adjust for available memory/API limits)

**Agent Retirement Strategy**: Graceful cleanup
- Agents removed from pool via `retire_agent(agent_id)`
- Broadcasts `agent_retired` event to dashboard
- Allows new agents to be created after retirement
- Used after project completion or error recovery

**Agent Reuse Benefits**:
- **Initialization Cost**: ~100ms per agent (LLM client, config)
- **Reuse Speedup**: < 10ms to assign task to idle agent
- **Memory Efficiency**: 10 agents vs. potentially 100s for project
- **API Rate Limits**: Fewer clients = easier rate limit management

### Alternatives Considered

**❌ Create-New-Every-Time**:
- **Rejected**: Initialization overhead (100ms/agent) unacceptable
- Would create 100+ agents for typical project
- Memory and rate limit exhaustion

**❌ Single Agent Per Type**:
- **Rejected**: No parallelism within agent type
- Frontend tasks would execute sequentially even when independent
- Defeats purpose of multi-agent coordination

**❌ Unbounded Pool**:
- **Rejected**: Resource exhaustion risk
- No backpressure mechanism
- Could spawn 100s of agents in pathological cases

**✅ Pool with Max Limit** (Chosen):
- Best of both worlds: reuse + bounded resources
- Predictable resource usage
- Parallel execution up to limit
- Simple to implement and reason about

---

## 2. Dependency Resolution with DAG

### Decision: Directed Acyclic Graph (DAG) with Kahn's Algorithm

**Rationale**:
- Task dependencies form natural graph structure
- DAG ensures no circular dependencies (prevents deadlocks)
- Kahn's algorithm provides efficient topological sort (O(V + E))
- Well-understood computer science problem with proven solutions
- Supports both sequential and parallel execution

**Data Structure**:
```python
class DependencyResolver:
    # Adjacency list: task_id -> set of task_ids it depends on
    self.dependencies: Dict[int, Set[int]] = defaultdict(set)

    # Reverse adjacency list: task_id -> set of task_ids that depend on it
    self.dependents: Dict[int, Set[int]] = defaultdict(set)

    # Track completed tasks
    self.completed_tasks: Set[int] = set()
```

**Why Two Adjacency Lists**:
- `dependencies`: Fast lookup of what task depends on (O(1))
- `dependents`: Fast lookup of what depends on task (O(1))
- Bidirectional access enables both blocking and unblocking operations

### Cycle Detection Algorithm

**Method**: Depth-First Search (DFS) with Recursion Stack

```python
def detect_cycles(self) -> bool:
    visited = set()
    rec_stack = set()

    def has_cycle(node: int) -> bool:
        visited.add(node)
        rec_stack.add(node)

        for dep in self.dependencies.get(node, set()):
            if dep not in visited:
                if has_cycle(dep):
                    return True
            elif dep in rec_stack:
                # Back edge found - cycle detected
                return True

        rec_stack.remove(node)
        return False

    for task_id in self.all_tasks:
        if task_id not in visited:
            if has_cycle(task_id):
                return True

    return False
```

**Key Insight**: Recursion stack tracks current DFS path
- If we encounter node already in `rec_stack`, it's a back edge → cycle
- If we encounter node in `visited` but not `rec_stack`, it's safe (cross edge)

**Cycle Detection Performance**: O(V + E)
- V = number of tasks
- E = number of dependencies
- Linear time complexity

### Task Blocking/Unblocking Mechanism

**Blocking Logic** (`get_ready_tasks()`):
```python
def get_ready_tasks(self) -> List[int]:
    ready = []
    for task_id in self.all_tasks:
        if task_id in self.completed_tasks:
            continue

        deps = self.dependencies.get(task_id, set())
        if not deps or deps.issubset(self.completed_tasks):
            ready.append(task_id)

    return ready
```

**Unblocking Logic** (`unblock_dependent_tasks()`):
```python
def unblock_dependent_tasks(self, completed_task_id: int) -> List[int]:
    self.completed_tasks.add(completed_task_id)

    dependent_ids = self.dependents.get(completed_task_id, set())
    unblocked = []

    for dep_id in dependent_ids:
        all_deps = self.dependencies.get(dep_id, set())
        if all_deps.issubset(self.completed_tasks):
            unblocked.append(dep_id)

    return unblocked
```

**Automatic Cascade**: When task completes, resolver finds all newly unblocked tasks
- Lead Agent calls `unblock_dependent_tasks(task_id)` after completion
- Returns list of task IDs now ready for execution
- Lead Agent assigns unblocked tasks to available agents
- Enables automatic parallelism when dependencies resolve

### Dependency Tracking in Database

**Schema Enhancement**:
```sql
ALTER TABLE tasks ADD COLUMN depends_on TEXT DEFAULT '[]';

-- Optional: Denormalized table for complex queries
CREATE TABLE task_dependencies (
    task_id TEXT NOT NULL,
    depends_on_task_id TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id),
    FOREIGN KEY (depends_on_task_id) REFERENCES tasks(id),
    UNIQUE(task_id, depends_on_task_id)
);
```

**Format**: JSON array in `depends_on` column
```json
{
  "id": 7,
  "title": "Login UI",
  "depends_on": "[5]",  // Depends on task 5
  "status": "pending"
}
```

**Alternative Formats Considered**:
- **Comma-separated IDs**: `"5,6,7"` - Simpler parsing, less formal
- **JSON array** (chosen): `"[5,6,7]"` - Standard format, better tooling support
- **Separate table only**: Joins required for every query

### Alternatives Considered

**❌ Direct Agent-to-Agent Communication**:
- **Rejected**: Race conditions between agents
- Complex synchronization primitives needed
- No centralized view of dependencies
- Harder to debug and reason about

**❌ Redis for Dependency State**:
- **Rejected**: Added infrastructure complexity
- External dependency for core feature
- SQLite sufficient for MVP scale (< 1000 tasks)
- Redis makes sense at scale (future optimization)

**❌ No Cycle Detection**:
- **Rejected**: Deadlocks inevitable with user-defined dependencies
- Silent failures hard to debug
- Better to fail fast with clear error message

**✅ DAG with DFS Cycle Detection** (Chosen):
- Well-understood algorithm
- Efficient (linear time)
- Clear error messages
- No additional infrastructure

---

## 3. State Management: React Context + useReducer

### Decision: Centralized State with Context + Reducer Pattern

**Rationale**:
- Multi-agent dashboard needs to coordinate state from 10+ concurrent agents
- Frequent updates (agent status changes, task assignments, completions)
- Context provides global state without prop drilling
- Reducer ensures predictable state transitions
- Performance: Can optimize with React.memo and useMemo

**Architecture**:
```typescript
// State container
interface AgentState {
  agents: Agent[];           // All active agents
  tasks: Task[];             // All tasks with dependencies
  activity: ActivityItem[];  // Recent activity feed
  lastUpdate: string;        // Timestamp for conflict resolution
}

// Action types (13 total)
type AgentAction =
  | { type: 'SET_AGENTS'; payload: Agent[] }
  | { type: 'AGENT_CREATED'; payload: Agent }
  | { type: 'AGENT_UPDATED'; payload: Partial<Agent> & { id: string } }
  | { type: 'AGENT_RETIRED'; payload: { id: string } }
  | { type: 'TASK_ASSIGNED'; payload: { taskId: number; agentId: string } }
  | { type: 'TASK_STATUS_CHANGED'; payload: { taskId: number; status: string } }
  | ... // 7 more action types
```

**Reducer Pattern**:
```typescript
function agentReducer(state: AgentState, action: AgentAction): AgentState {
  switch (action.type) {
    case 'AGENT_CREATED':
      return {
        ...state,
        agents: [...state.agents, action.payload],
        lastUpdate: new Date().toISOString()
      };

    case 'AGENT_UPDATED':
      return {
        ...state,
        agents: state.agents.map(a =>
          a.id === action.payload.id
            ? { ...a, ...action.payload }
            : a
        ),
        lastUpdate: new Date().toISOString()
      };

    // ... 11 more cases
  }
}
```

### WebSocket Integration with State Sync

**Message → Action Mapping**:
```typescript
function processWebSocketMessage(message: WebSocketMessage): AgentAction | null {
  switch (message.type) {
    case 'agent_created':
      return {
        type: 'AGENT_CREATED',
        payload: {
          id: message.agent_id,
          type: message.agent_type,
          status: 'idle',
          tasksCompleted: 0
        }
      };

    case 'task_assigned':
      return {
        type: 'TASK_ASSIGNED',
        payload: {
          taskId: message.task_id,
          agentId: message.agent_id
        }
      };

    // ... 7 more message types
  }
}
```

**Provider with WebSocket Listener**:
```typescript
export function AgentStateProvider({ projectId, children }) {
  const [state, dispatch] = useReducer(agentReducer, getInitialState());

  useEffect(() => {
    const ws = getWebSocketClient(`/projects/${projectId}`);

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      const action = processWebSocketMessage(message);

      if (action) {
        dispatch(action);
      }
    };

    return () => ws.close();
  }, [projectId]);

  return (
    <AgentStateContext.Provider value={{ state, dispatch }}>
      {children}
    </AgentStateContext.Provider>
  );
}
```

### Performance with 10 Concurrent Agents

**Optimizations Implemented**:

1. **React.memo on Dashboard Components**:
```typescript
export const AgentCard = React.memo(({ agent }) => {
  // Only re-renders when agent prop changes
});
```

2. **useMemo for Derived State**:
```typescript
const activeAgents = useMemo(
  () => agents.filter(a => a.status !== 'offline'),
  [agents]
);
```

3. **Selective Subscription** (future):
```typescript
// Only subscribe to specific agent updates
const backend1 = useAgent('backend-1'); // Subscribes to backend-1 only
```

**Benchmarks** (10 concurrent agents):
- **Update Latency**: < 50ms from WebSocket message to React re-render
- **Memory**: ~2MB for agent state (10 agents × ~200KB metadata each)
- **Render Time**: < 16ms per update (60 FPS maintained)

### Timestamp Conflict Resolution

**Problem**: Multiple updates from different agents can arrive out-of-order

**Solution**: Last-write-wins with backend timestamps
```typescript
if (action.payload.timestamp > state.lastUpdate) {
  // Apply update
} else {
  // Discard stale update
}
```

**Why Backend Timestamps**:
- Client clocks can be skewed
- Backend is source of truth
- Consistent ordering across all clients

### Alternatives Considered

**❌ Redux**:
- **Rejected**: Boilerplate overhead for this use case
- Overkill for 10 agents and simple actions
- Context + useReducer provides 80% of Redux benefits with 20% complexity

**❌ Zustand**:
- **Rejected**: External dependency
- Not significantly simpler than Context + useReducer
- Team already familiar with Context pattern

**❌ Component-Local State**:
- **Rejected**: Props drilling nightmare with nested components
- No centralized view for debugging
- Duplicate WebSocket listeners per component

**❌ Direct DOM Manipulation**:
- **Rejected**: Bypasses React reconciliation
- Harder to maintain
- No state history for debugging

**✅ Context + useReducer** (Chosen):
- Zero external dependencies
- Excellent debugging (Redux DevTools compatible with effort)
- Team already familiar with pattern
- Scales to 10 agents without performance issues

---

## 4. Broadcast Coordination with WebSocket

### Decision: Centralized WebSocket Broadcasts from Backend

**Rationale**:
- Single source of truth for agent lifecycle events
- All connected clients receive consistent updates
- Backend controls message ordering
- Simplifies client-side logic (just listen and update state)

**WebSocket Event Types for Multi-Agent**:
```python
# Agent lifecycle
- agent_created:   { agent_id, agent_type, tasks_completed }
- agent_retired:   { agent_id }

# Task coordination
- task_assigned:   { task_id, agent_id, agent_type }
- task_blocked:    { task_id, blocked_by: [task_ids] }
- task_unblocked:  { task_id, unblocked_by: task_id }

# Agent status
- agent_status_changed: { agent_id, status, current_task }
```

**Broadcast Functions** (`websocket_broadcasts.py`):
```python
async def broadcast_agent_created(
    manager,
    project_id: int,
    agent_id: str,
    agent_type: str,
    tasks_completed: int
) -> None:
    message = {
        "type": "agent_created",
        "project_id": project_id,
        "agent_id": agent_id,
        "agent_type": agent_type,
        "tasks_completed": tasks_completed,
        "timestamp": datetime.now(UTC).isoformat()
    }
    await manager.broadcast(message)
```

### Thread-Safe Broadcasting Challenges (Sprint 4)

**Problem**: Agent pool uses RLock, but WebSocket broadcasts are async
```python
class AgentPoolManager:
    def create_agent(self, agent_type: str) -> str:
        with self.lock:  # Synchronous context
            # ... create agent ...

            # Need to broadcast, but we're in sync context!
            self._broadcast_async(...)  # ⚠️ Problematic
```

**Sprint 4 Solution**: `_broadcast_async()` Wrapper
```python
def _broadcast_async(self, project_id, agent_id, agent_type, event_type):
    if not self.ws_manager:
        return

    try:
        loop = asyncio.get_running_loop()

        if event_type == "agent_created":
            loop.create_task(
                broadcast_agent_created(
                    self.ws_manager,
                    project_id,
                    agent_id,
                    agent_type,
                    tasks_completed
                )
            )
    except RuntimeError:
        # No event loop running (testing)
        logger.debug(f"Skipped broadcast: {event_type}")
```

**Why This Works** (Sprint 4):
- `get_running_loop()` finds the event loop if already running
- `create_task()` schedules coroutine without blocking
- `try/except` handles testing context (no loop)

**Why This is Problematic** (Discovered in Sprint 5):
- `get_running_loop()` fails if called from thread without loop
- Silent failures in some contexts (`except RuntimeError`)
- Creates race conditions with event loop

**Sprint 5 Improvement**: Full Async Migration
```python
class AgentPoolManager:
    async def create_agent(self, agent_type: str) -> str:
        async with self.async_lock:  # Async lock instead of RLock
            # ... create agent ...

            # Direct await - no wrapper needed
            await broadcast_agent_created(
                self.ws_manager,
                project_id,
                agent_id,
                agent_type,
                tasks_completed
            )
```

### Event Loop Considerations

**Sprint 4 Threading Model**:
- FastAPI runs in asyncio event loop
- Agent pool operations called from sync endpoints
- `run_in_executor()` used to bridge sync/async
- WebSocket broadcasts scheduled via `create_task()`

**Sprint 5 Async Model**:
- All agent operations are async
- Direct `await` for all I/O operations
- No threading, no executor, no wrapper methods
- Simpler, faster, more reliable

**Key Insight**: Threading model was root cause of complexity
- Forced sync/async boundary management
- Required wrapper methods like `_broadcast_async()`
- Created event loop deadlock potential
- Sprint 5 removed this entirely

### Alternatives Considered

**❌ Polling from Frontend**:
- **Rejected**: Inefficient for real-time updates
- 100ms polling × 10 clients = 100 req/sec load
- 500ms+ latency for updates

**❌ Server-Sent Events (SSE)**:
- **Rejected**: One-way communication only
- Would need separate HTTP endpoints for commands
- WebSocket provides bidirectional channel

**❌ Redis Pub/Sub for Broadcasting**:
- **Rejected**: External dependency
- Adds latency (extra hop)
- Complexity for horizontal scaling (future consideration)

**❌ Agent-to-Agent P2P**:
- **Rejected**: N² connection complexity
- No centralized coordination
- Race conditions inevitable

**✅ Centralized WebSocket** (Chosen):
- FastAPI WebSocket support built-in
- Low latency (< 10ms)
- Scales to 10s of concurrent clients
- Simple debugging (all messages visible in server logs)

---

## 5. Alternative Approaches Considered

### Direct Agent-to-Agent Communication

**Concept**: Agents communicate directly to coordinate tasks

**Why Rejected**:
- **Race Conditions**: Multiple agents updating shared state
- **Deadlock Risk**: Agent A waits for Agent B, Agent B waits for Agent A
- **No Global View**: Hard to visualize or debug coordination
- **Complex Synchronization**: Would need distributed locks/semaphores

**When It Makes Sense**:
- Very large scale (100+ agents) where centralized coordination is bottleneck
- Specialized use cases (e.g., swarm algorithms)
- Not needed for MVP (< 10 agents)

---

### Redis for State Sharing

**Concept**: Use Redis as shared state backend for agents

**Why Rejected**:
- **Added Complexity**: External dependency, deployment overhead
- **Scale Not Needed**: SQLite handles < 1000 tasks easily
- **Latency**: Redis adds network hop (even localhost)
- **Persistence**: SQLite already provides persistence

**When It Makes Sense**:
- Horizontal scaling (multiple backend servers)
- 100s of concurrent agents
- Distributed deployment
- Future optimization, not MVP requirement

**Potential Future Adoption**:
```python
# Phase 1: SQLite (current)
db = Database("project.db")

# Phase 2: Redis cache layer (future)
cache = Redis("localhost:6379")
db = Database("project.db", cache=cache)
```

---

### Actor Model (Akka-style)

**Concept**: Each agent is an actor with mailbox, processes messages sequentially

**Why Rejected**:
- **Overkill for MVP**: Python lacks native actor framework (would need Pykka, Thespian)
- **Complexity**: Actor supervision trees, message routing, fault tolerance
- **Learning Curve**: Team not familiar with actor model
- **Benefits Not Needed**: Agent pool + DAG solves coordination without actors

**When It Makes Sense**:
- Fault-tolerance requirements (actor supervision)
- Location transparency (distributed actors)
- Complex state machines per agent
- Not needed for Sprint 4 MVP

**Actor Model Benefits We Don't Need**:
- **Supervision Trees**: Agent failures handled by simple retry logic
- **Location Transparency**: All agents run on same machine in MVP
- **Message Ordering**: WebSocket broadcasts already ordered

---

### Polling vs. WebSocket for Updates

**Polling Approach**:
```typescript
// Poll every 500ms
setInterval(async () => {
  const agents = await fetch('/api/agents');
  setAgents(agents);
}, 500);
```

**Why Rejected**:
- **Inefficient**: 2 requests/sec × 10 clients = 20 req/sec even when idle
- **Latency**: Average 250ms update delay (half polling interval)
- **Server Load**: Constant database queries
- **Scaling**: Doesn't scale to more clients

**WebSocket Approach** (Chosen):
```typescript
ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  dispatch(processWebSocketMessage(message));
};
```

**Benefits**:
- **Efficient**: Messages only sent when state changes
- **Low Latency**: < 10ms from event to client
- **Scalable**: No polling overhead
- **Bidirectional**: Can send commands to backend

**Hybrid Approach** (Future):
```typescript
// WebSocket for real-time updates
ws.onmessage = handleMessage;

// Polling fallback if WebSocket unavailable
if (ws.readyState !== WebSocket.OPEN) {
  pollInterval = setInterval(fetchAgents, 5000); // 5 sec fallback
}
```

---

## 6. Key Design Patterns Summary

### Agent Pool Pattern
- **Pattern**: Object pool with max capacity
- **Thread-Safety**: RLock for pool operations (Sprint 4), async locks (Sprint 5)
- **Lifecycle**: create → idle → busy → idle → retire
- **Benefit**: 10x faster task assignment via reuse

### Dependency Resolution Pattern
- **Pattern**: DAG with bidirectional adjacency lists
- **Algorithm**: Kahn's topological sort + DFS cycle detection
- **Complexity**: O(V + E) for all operations
- **Benefit**: Automatic parallelism when dependencies allow

### State Management Pattern
- **Pattern**: Flux-inspired unidirectional data flow
- **Implementation**: React Context + useReducer
- **Updates**: WebSocket → Action → Reducer → State → UI
- **Benefit**: Predictable state transitions, easy debugging

### Broadcast Coordination Pattern
- **Pattern**: Centralized pub/sub via WebSocket
- **Guarantees**: Message ordering, at-least-once delivery
- **Conflict Resolution**: Last-write-wins with timestamps
- **Benefit**: Consistent state across all clients

---

## 7. Performance Characteristics

### Agent Pool Operations
| Operation | Time Complexity | Notes |
|-----------|-----------------|-------|
| `get_or_create_agent()` | O(n) worst case | n = pool size (max 10) |
| `create_agent()` | O(1) | Hash table insert |
| `mark_agent_busy/idle()` | O(1) | Hash table lookup |
| `retire_agent()` | O(1) | Hash table delete |

### Dependency Resolution Operations
| Operation | Time Complexity | Notes |
|-----------|-----------------|-------|
| `build_dependency_graph()` | O(V + E) | V = tasks, E = dependencies |
| `get_ready_tasks()` | O(V) | Check all tasks |
| `unblock_dependent_tasks()` | O(d) | d = # dependents of completed task |
| `detect_cycles()` | O(V + E) | DFS traversal |
| `topological_sort()` | O(V + E) | Kahn's algorithm |

### WebSocket Broadcast Latency
| Metric | Value | Notes |
|--------|-------|-------|
| Backend processing | < 5ms | Serialize message, broadcast |
| Network latency | < 5ms | Localhost WebSocket |
| React state update | < 20ms | Reducer + re-render |
| **Total latency** | **< 30ms** | Event → UI update |

### Memory Footprint (10 Agents)
| Component | Memory | Notes |
|-----------|--------|-------|
| Agent pool metadata | ~10 KB | 10 agents × ~1KB each |
| Dependency graph | ~5 KB | 100 tasks × ~50 bytes |
| WebSocket connections | ~500 KB | 10 clients × ~50KB each |
| React state | ~2 MB | Agent + task metadata |
| **Total** | **~2.5 MB** | Negligible overhead |

---

## 8. Technical Debt and Future Work

### Sprint 4 Technical Debt (Resolved in Sprint 5)

**Threading Model Complexity**:
- **Debt**: RLock, `run_in_executor()`, `_broadcast_async()` wrapper
- **Impact**: Event loop deadlocks, silent broadcast failures
- **Resolution**: Full async migration in Sprint 5 (issue 048)

**Broadcast Reliability**:
- **Debt**: Silent failures in `_broadcast_async()` (catch RuntimeError)
- **Impact**: Dashboard occasionally misses updates
- **Resolution**: Direct `await` broadcasts in Sprint 5

### Future Optimizations

**Horizontal Scaling** (Post-MVP):
- Replace SQLite with PostgreSQL
- Add Redis for state sharing across backend instances
- Load balancer for WebSocket connections

**Advanced Agent Routing** (Sprint 9):
- Capability-based matching (beyond simple type matching)
- Agent skill profiles and task requirements
- Dynamic routing based on agent performance

**Bottleneck Detection** (Deferred):
- Identify tasks blocking 3+ dependent tasks
- Visual highlighting in dashboard
- Suggest parallelization opportunities

**Subagent Spawning** (Deferred):
- Specialist subagents (code review, accessibility, security)
- Hierarchical reporting to parent agent
- Resource limits for subagent trees

---

## 9. Lessons Learned

### What Worked Well

1. **Agent Pool Pattern**: Significant performance improvement via reuse
2. **DAG for Dependencies**: Clean abstraction, catches cycles early
3. **Context + useReducer**: Excellent balance of simplicity and power
4. **WebSocket Broadcasts**: Low latency, simple to implement

### What Was Challenging

1. **Threading vs. Async**: Root cause of multiple bugs, required Sprint 5 refactor
2. **Cycle Detection**: Edge cases (self-dependencies, transitive cycles) needed careful testing
3. **State Synchronization**: Race conditions when multiple agents update same task

### What We'd Do Differently

1. **Start with Async**: Should have used AsyncAnthropic from Sprint 3
2. **More Integration Tests**: Multi-agent scenarios harder to test than unit tests
3. **Earlier Performance Testing**: Discovered 10-agent limit via manual testing

---

## 10. References

### Internal Documentation
- **Sprint 4 Spec**: `specs/004-multi-agent-coordination/spec.md`
- **Sprint 4 Plan**: `specs/004-multi-agent-coordination/plan.md`
- **Sprint 4 Retrospective**: `sprints/sprint-04-multi-agent.md`
- **Sprint 5 Async Migration**: `specs/048-async-worker-agents/research.md`

### External Resources
- **DAG Algorithms**: "Introduction to Algorithms" (CLRS), Chapter 22
- **React Context**: https://react.dev/learn/passing-data-deeply-with-context
- **WebSocket Protocol**: RFC 6455
- **Anthropic Async SDK**: https://github.com/anthropics/anthropic-sdk-python#async-usage

### Code References
- `codeframe/agents/agent_pool_manager.py` - Agent pool implementation
- `codeframe/agents/dependency_resolver.py` - DAG and cycle detection
- `codeframe/ui/websocket_broadcasts.py` - Multi-agent broadcast functions
- `web-ui/src/components/AgentStateProvider.tsx` - Context + useReducer
- `web-ui/src/reducers/agentReducer.ts` - State reducer with 13 action types

---

**Last Updated**: 2025-11-08
**Author**: CodeFRAME Team
**Sprint**: 4 (Multi-Agent Coordination)
