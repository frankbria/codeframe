# codeframe Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-11-23

## Documentation Navigation

**For efficient documentation navigation**, see [AGENTS.md](AGENTS.md).

Quick reference:
- **Current sprint**: [SPRINTS.md](SPRINTS.md) (sprint timeline index)
- **Sprint details**: `sprints/sprint-NN-name.md` (individual sprint summaries)
- **Feature specs**: `specs/{feature}/` (detailed implementation guides)
- **Architecture**: [CODEFRAME_SPEC.md](CODEFRAME_SPEC.md) (system design)

## Documentation Structure

- **`sprints/`** - Sprint execution records (WHAT was delivered WHEN)
- **`specs/`** - Feature implementation specifications (HOW to implement)
- **Root** - Project-wide documentation (coding standards, architecture)

## Active Technologies
- Python 3.11 + anthropic (AsyncAnthropic), asyncio, FastAPI, websockets (048-async-worker-agents)
- Python 3.11+ (backend), TypeScript 5.3+ (frontend) + FastAPI, AsyncAnthropic, React 18, Tailwind CSS, aiosqlite, websockets (049-human-in-loop)
- SQLite with async support (aiosqlite) - blockers table schema already exists (049-human-in-loop)
- Python 3.11+ (backend), TypeScript 5.3+ (frontend dashboard) + FastAPI, AsyncAnthropic, React 18, aiosqlite, tiktoken (for token counting) (007-context-management)
- SQLite with async support (aiosqlite) - context_items table schema already exists (007-context-management)
- Python 3.11+ (backend), TypeScript 5.3+ (frontend) + FastAPI, AsyncAnthropic, React 18, Tailwind CSS, aiosqlite, tiktoken, TestSprite (MCP) (015-review-polish)
- SQLite (state.db) + file system (.codeframe/checkpoints/, git commits) (015-review-polish)

## Project Structure
```
/
├── sprints/          # Sprint summaries (80-120 lines each)
├── specs/            # Feature specifications (400-800 lines each)
├── codeframe/        # Python package
├── web-ui/           # React frontend
├── tests/            # Test suite
└── docs/             # Additional documentation
```

## Commands
```bash
pytest                 # Run all tests
pytest tests/test_*worker_agent.py  # Worker agent tests (async)
ruff check .           # Lint code
cd web-ui && npm test  # Frontend tests
```

## Code Style
- **Backend**: Python 3.11+ with async/await pattern, type hints, comprehensive tests
- **Frontend**: TypeScript 5.3+ with React, strict mode, 85%+ test coverage
- **Conventions**: Follow existing patterns in codebase

## Context Management for AI Conversations

### Quality-First Development
See `.claude/rules.md` for comprehensive context management guidelines including:
- **Token budget**: ~50,000 tokens per conversation (warning at 45k)
- **Checkpoint system**: Every 5 AI responses
- **Auto-reset triggers**: Quality degradation >10%, response count >15-20, token budget >45k
- **Context handoff template**: For smooth conversation resets

### Quality Monitoring
Use `scripts/quality-ratchet.py` to track quality metrics:
```bash
# Check current quality (auto-suggests reset if degradation detected)
python scripts/quality-ratchet.py check

# Record baseline metrics
python scripts/quality-ratchet.py record --coverage 87.5 --pass-rate 100.0 --response-count 5

# View quality trends
python scripts/quality-ratchet.py show
```

**Auto-suggestion**: When quality degrades >10%, the tool recommends context reset with handoff template from `.claude/rules.md`.

## Recent Changes
- 015-review-polish (Sprint 10 - COMPLETE): MVP COMPLETE! 🎉
  * **Quality Gates System**: Multi-stage pre-completion checks (tests → type → coverage → review)
  * **Checkpoint & Recovery**: Git + SQLite + context snapshots for project state rollback
  * **Metrics & Cost Tracking**: Real-time token usage and cost analytics (Sonnet 4.5, Opus 4, Haiku 4)
  * **End-to-End Testing**: TestSprite + Playwright for comprehensive E2E workflow validation
  * **Database Changes**: Added code_reviews, token_usage tables; extended tasks, checkpoints tables
  * **Performance**: Review <30s, quality gates <2min, checkpoint create <10s/restore <30s, metrics <50ms
  * **Testing**: 550+ tests, 88%+ coverage, 100% pass rate
  * **Technologies**: Python 3.11+, TypeScript 5.3+, FastAPI, React 18, Tailwind CSS, aiosqlite, tiktoken, TestSprite (MCP)
- 014-session-lifecycle: Added Session Lifecycle Management - Auto-save/restore work context across CLI restarts (file-based storage in `.codeframe/session_state.json`)
- 010-server-start-command: Added CLI 'serve' command (--port, --reload, --no-browser flags), port validation utilities (port_utils.py), 19 tests with 100% coverage on utilities, no database changes
  * **Multi-Agent Support**: Multiple agents can now collaborate on same project
  * Added `agent_id` column to `context_items` schema
  * Updated all database methods to accept `(project_id, agent_id)` scoping
  * Added `project_id` parameter to `WorkerAgent.__init__()` and all context methods
  * Updated `ContextManager` methods for multi-project support
  * Updated API endpoints to accept `project_id` query parameter
  * **Before**: One project per agent (broken architecture)
  * **After**: Multiple agents (orchestrator, backend, frontend, test, review) collaborate on same project
  * **Tests**: 59/59 passing (100%) - Full multi-agent test coverage
  * Phase 2: Foundational layer (Pydantic models, migrations, database methods, TokenCounter)
  * Phase 3: Context item storage (save/load/get context with persistence)
  * Phase 4: Importance scoring with hybrid exponential decay algorithm (T027-T036)
  * Phase 5: Automatic tier assignment HOT/WARM/COLD (T037-T043, T046)
  * **Formula**: score = 0.4 × type_weight + 0.4 × age_decay + 0.2 × access_boost
  * **Tiers**: HOT (≥0.8), WARM (0.4-0.8), COLD (<0.4)

<!-- MANUAL ADDITIONS START -->
## Frontend State Management Architecture (Phase 5.2)

### Context + Reducer Pattern
The Dashboard uses React Context with useReducer for centralized state management:

- **AgentStateContext** (`web-ui/src/contexts/AgentStateContext.ts`): Global state container
- **agentReducer** (`web-ui/src/reducers/agentReducer.ts`): Pure reducer with 13 action types
- **AgentStateProvider** (`web-ui/src/components/AgentStateProvider.tsx`): Context provider with WebSocket integration
- **useAgentState** (`web-ui/src/hooks/useAgentState.ts`): Custom hook for consuming state

### Key Features
- **Multi-Agent Support**: Handles up to 10 concurrent agents with independent state tracking
- **Real-Time Updates**: WebSocket integration with 9 event types (agent_created, task_assigned, etc.)
- **Automatic Reconnection**: Exponential backoff (1s → 30s) with full state resync
- **Timestamp Conflict Resolution**: Last-write-wins using backend timestamps
- **Performance Optimizations**: React.memo on all Dashboard sub-components, useMemo for derived state
- **Error Boundaries**: ErrorBoundary component wraps AgentStateProvider for graceful error handling

### File Locations
```
web-ui/src/
├── contexts/AgentStateContext.ts
├── components/
│   ├── AgentStateProvider.tsx
│   └── ErrorBoundary.tsx
├── reducers/agentReducer.ts
├── hooks/useAgentState.ts
├── lib/
│   ├── websocketMessageMapper.ts
│   ├── agentStateSync.ts
│   └── validation.ts
└── types/agentState.ts
```

### Testing
- 90 unit & integration tests covering reducer, WebSocket mapping, state sync, and Dashboard integration
- Test files located in `web-ui/__tests__/`

## Context Management System (007-context-management)

### Overview
The Context Management system implements intelligent tiered memory (HOT/WARM/COLD) with importance scoring to enable long-running autonomous agent sessions (4+ hours) by reducing token usage 30-50% through strategic context archival and restoration.

### Core Concepts

#### Tiered Memory System
- **HOT Tier** (importance_score ≥ 0.8): Always loaded, critical context items
- **WARM Tier** (0.4 ≤ importance_score < 0.8): On-demand loading, semi-important items
- **COLD Tier** (importance_score < 0.4): Archived during flash save, rarely accessed

#### Importance Scoring Algorithm
```python
score = 0.4 × type_weight + 0.4 × age_decay + 0.2 × access_boost

# Type weights: TASK (1.0), CODE (0.9), ERROR (0.8), PRD_SECTION (0.7), etc.
# Age decay: Exponential decay over time (half-life = 24 hours)
# Access boost: 0.1 per access, capped at 0.5
```

#### Flash Save Mechanism
When context approaches token limit (80% of 180k = 144k tokens):
1. Create checkpoint with full context state (JSON serialization)
2. Archive COLD tier items (delete from active context)
3. Retain HOT and WARM tier items
4. Achieve 30-50% token reduction

### Usage Patterns

#### 1. Creating Context Items
```python
from codeframe.agents.worker_agent import WorkerAgent
from codeframe.core.models import ContextItemType

agent = WorkerAgent(agent_id="backend-001", project_id=123, db=db)

# Save a task to context
await agent.save_context_item(
    item_type=ContextItemType.TASK,
    content="Implement user authentication with JWT tokens"
)

# Save code snippet
await agent.save_context_item(
    item_type=ContextItemType.CODE,
    content="def authenticate_user(token: str) -> User: ..."
)
```

#### 2. Loading Context
```python
# Load all HOT tier items (always loaded)
hot_items = await agent.load_context(tier="hot")

# Load specific tier
warm_items = await agent.load_context(tier="warm", limit=50)

# Load all active context
all_items = await agent.load_context()  # Returns HOT + WARM
```

#### 3. Updating Tiers
```python
from codeframe.lib.context_manager import ContextManager

context_mgr = ContextManager(db=db)

# Recalculate scores and reassign tiers for an agent
updated_count = context_mgr.update_tiers_for_agent(
    project_id=123,
    agent_id="backend-001"
)
print(f"Updated {updated_count} items")
```

#### 4. Flash Save Operation
```python
# Check if flash save should be triggered
if await agent.should_flash_save():
    # Trigger flash save
    result = await agent.flash_save()

    print(f"Checkpoint ID: {result['checkpoint_id']}")
    print(f"Token reduction: {result['reduction_percentage']}%")
    print(f"Items archived: {result['items_archived']}")
```

#### 5. Accessing Context Stats (API)
```bash
# Get context statistics for an agent
GET /api/agents/{agent_id}/context/stats?project_id=123

# Response:
{
  "agent_id": "backend-001",
  "project_id": 123,
  "hot_count": 20,
  "warm_count": 50,
  "cold_count": 30,
  "total_tokens": 50000,
  "token_usage_percentage": 27.8
}

# List context items with tier filtering
GET /api/agents/{agent_id}/context/items?project_id=123&tier=hot&limit=20

# Trigger flash save
POST /api/agents/{agent_id}/flash-save?project_id=123&force=false
```

### Frontend Components

#### ContextPanel (Main Container)
```tsx
import { ContextPanel } from './components/context/ContextPanel';

// Display context overview with auto-refresh
<ContextPanel
  agentId="backend-001"
  projectId={123}
  refreshInterval={5000}  // 5 seconds
/>
```

#### ContextTierChart (Visual Distribution)
```tsx
import { ContextTierChart } from './components/context/ContextTierChart';

// Show tier distribution chart
<ContextTierChart stats={contextStats} />
```

#### ContextItemList (Items Table)
```tsx
import { ContextItemList } from './components/context/ContextItemList';

// Display filterable, paginated items table
<ContextItemList
  agentId="backend-001"
  projectId={123}
  pageSize={20}
/>
```

### Best Practices

1. **Regular Score Updates**: Run `update_tiers_for_agent()` periodically (e.g., every 5 minutes) to keep tier assignments fresh
2. **Flash Save Monitoring**: Check `should_flash_save()` after major context additions to prevent token overflow
3. **Tier-Aware Loading**: Load only HOT tier initially, fetch WARM on-demand to minimize latency
4. **Checkpoint Recovery**: Use checkpoints to restore context after crashes or interruptions
5. **Multi-Agent Context**: Each agent maintains independent context scoped by `(project_id, agent_id)`

### Performance Characteristics
- Context tier lookup: <50ms
- Flash save operation: <2 seconds
- Importance score calculation: <10ms per item
- Context load (1000 items): <200ms
- Token reduction: 30-50% after flash save

### File Locations
```
codeframe/
├── lib/
│   ├── context_manager.py        # Core context management logic
│   ├── importance_scorer.py      # Scoring algorithm
│   └── token_counter.py          # Token counting with tiktoken
├── persistence/
│   └── database.py               # Context storage methods
└── agents/
    └── worker_agent.py           # Agent context interface

web-ui/src/
├── types/context.ts              # TypeScript type definitions
├── api/context.ts                # API client functions
└── components/context/
    ├── ContextPanel.tsx          # Main panel component
    ├── ContextTierChart.tsx      # Tier distribution chart
    └── ContextItemList.tsx       # Items table with filtering

tests/
├── context/                      # Unit tests (21 tests)
│   ├── test_flash_save.py
│   ├── test_token_counting.py
│   ├── test_checkpoint_restore.py
│   └── test_context_stats.py
└── integration/                  # Integration tests (2 tests)
    └── test_flash_save_workflow.py

web-ui/__tests__/components/
└── ContextPanel.test.tsx         # Frontend tests (6 tests)
```

### Testing
- **Backend**: 23 unit tests + 2 integration tests = 25 tests (100% passing)
- **Frontend**: 6 component tests (100% passing)
- **Total**: 31 tests covering all context management functionality

## Session Lifecycle Management (014-session-lifecycle)

### Overview
The Session Lifecycle Management feature automatically saves and restores work context across CLI restarts, ensuring developers never lose track of what was completed or what's next.

**Key Benefits**:
- 🔄 **Automatic context restoration** - No manual re-orientation needed
- 📋 **Next actions queue** - Know exactly what to do next
- 📊 **Progress visibility** - See project progress at a glance
- ⚠️ **Blocker awareness** - Stay informed about issues requiring human input

### Core Concepts

#### Session State File
- **Location**: `.codeframe/session_state.json` (per project)
- **Format**: JSON with human-readable formatting
- **Scope**: Per-project (each project has its own session state)
- **Persistence**: Saved on CLI exit (Ctrl+C or normal termination)
- **Restoration**: Loaded automatically on CLI start

#### Session State Schema
```json
{
  "last_session": {
    "summary": "Completed Task #27 (JWT refresh tokens), Task #28 (Add token validation)",
    "completed_tasks": [27, 28],
    "timestamp": "2025-11-20T10:30:00"
  },
  "next_actions": [
    "Fix JWT validation in kong-gateway.ts (Task #29)",
    "Add refresh token tests (Task #30)",
    "Update auth documentation (Task #31)"
  ],
  "current_plan": "Implement OAuth 2.0 authentication with JWT tokens",
  "active_blockers": [
    {
      "id": 5,
      "question": "Which OAuth provider should we use for SSO?",
      "priority": "high"
    }
  ],
  "progress_pct": 68.5
}
```

### Usage Patterns

#### 1. CLI Session Workflow
```bash
# Start or resume project (auto-restores session)
codeframe start my-app

# Output when session exists:
# 📋 Restoring session...
#
# Last Session:
#   Summary: Completed Task #27 (JWT refresh tokens)
#   Time: 2 hours ago
#
# Next Actions:
#   1. Fix JWT validation in kong-gateway.ts
#   2. Add refresh token tests
#   3. Update auth documentation
#
# Progress: 68% (27/40 tasks complete)
# Blockers: None
#
# Press Enter to continue or Ctrl+C to cancel...

# Clear saved session state
codeframe clear-session my-app
# Output: ✓ Session state cleared
```

#### 2. API Access
```bash
# Get session state for a project
GET /api/projects/{id}/session

# Response:
{
  "last_session": {
    "summary": "Completed Task #27 (JWT refresh tokens)",
    "timestamp": "2025-11-20T10:30:00"
  },
  "next_actions": [
    "Fix JWT validation in kong-gateway.ts"
  ],
  "progress_pct": 68.5,
  "active_blockers": []
}
```

#### 3. Programmatic Usage
```python
from codeframe.core.session_manager import SessionManager

# Initialize session manager
session_mgr = SessionManager(project_path="/path/to/project")

# Save session state
session_mgr.save_session({
    'summary': 'Completed Task #27, Task #28',
    'completed_tasks': [27, 28],
    'next_actions': ['Fix validation (Task #29)'],
    'current_plan': 'Build API',
    'active_blockers': [],
    'progress_pct': 50.0
})

# Load session state
state = session_mgr.load_session()
if state:
    print(f"Last session: {state['last_session']['summary']}")
    print(f"Progress: {state['progress_pct']}%")

# Clear session
session_mgr.clear_session()
```

### Best Practices

1. **Let sessions save automatically** - Always exit with Ctrl+C or normal termination
2. **Review session context on startup** - Read what was done and what's next
3. **Clear stale sessions** - Use `clear-session` if context becomes outdated
4. **Monitor progress** - Check progress percentage to stay on track

### Error Handling

#### Corrupted Session Files
When a session file contains invalid JSON:
- `load_session()` returns `None` (no crash)
- User sees "Starting new session..." message
- CLI continues to work normally
- Use `codeframe clear-session` to remove corrupted file

#### Missing Session Files
- First run or after `clear-session` command
- User sees "Starting new session..." (normal behavior)
- No error messages

### Performance Characteristics
- **Session save time**: ~10ms (negligible)
- **Session load time**: ~5ms (negligible)
- **File size**: ~1-2 KB (typical)
- **Storage**: Local file system only (no network)

### Security Considerations
- **File permissions**: Restricted to owner only (0o600)
- **No sensitive data**: Sessions don't store tokens, passwords, or credentials
- **Local only**: Session files never transmitted over network
- **User-owned**: Each user has their own session files

### File Locations
```
codeframe/
├── core/
│   └── session_manager.py        # Core session management logic
└── agents/
    └── lead_agent.py             # Session lifecycle hooks (on_session_start, on_session_end)

tests/
├── agents/
│   └── test_lead_agent_session.py  # Unit tests (20 tests)
├── cli/
│   └── test_cli_session.py         # CLI command tests (11 tests)
├── api/
│   └── test_api_session.py         # API endpoint tests (13 tests)
└── integration/
    └── test_session_lifecycle.py   # Integration tests (10 tests)
```

### Testing
- **Unit Tests**: 44 tests (agents, CLI, API)
- **Integration Tests**: 10 tests (full lifecycle, corruption handling, Ctrl+C behavior)
- **Total**: 54 tests (100% passing)
- **Coverage**: 93.75% for session_manager.py

## Sprint 10: Review & Polish - MVP COMPLETE! (015-review-polish)

### Overview
Sprint 10 completes the CodeFRAME MVP by adding production-ready quality enforcement, state management, and cost tracking. Agents can now work autonomously for 8+ hours with comprehensive quality gates preventing bad code, checkpoints enabling rollback to known-good states, and detailed metrics tracking costs.

**Key Capabilities**:
- 🛡️ **Quality Gates** - Multi-stage pre-completion checks block bad code automatically
- 💾 **Checkpoint & Recovery** - Save/restore project state (Git + DB + context)
- 💰 **Metrics & Cost Tracking** - Real-time token usage and cost analytics
- 🧪 **E2E Testing** - Comprehensive workflow validation with TestSprite + Playwright

### Quality Gates System (User Story 2)

#### Pre-Completion Workflow
Quality gates run **before** marking tasks complete, preventing bad code from being "done":

```python
# In WorkerAgent.complete_task()
async def complete_task(self, task: Task) -> TaskResult:
    # Stage 1: Run tests
    test_result = await self._run_tests(task)
    if not test_result.passed:
        return self._create_blocker(task, "Tests failed", test_result)

    # Stage 2: Type checking
    type_result = await self._run_type_check(task)
    if not type_result.passed:
        return self._create_blocker(task, "Type errors", type_result)

    # Stage 3: Coverage check
    coverage = await self._check_coverage(task)
    if coverage < 0.85:
        return self._create_blocker(task, f"Coverage {coverage}% < 85%")

    # Stage 4: Code review (Review Agent)
    review_result = await self._trigger_review_agent(task)
    if review_result.has_critical_issues:
        return self._create_blocker(task, "Critical review findings", review_result)

    # All gates passed
    return TaskResult(status="completed")
```

#### API Usage
```bash
# Get quality gate status for a task
GET /api/tasks/{task_id}/quality-gates?project_id=1

# Manually trigger quality gates
POST /api/tasks/{task_id}/quality-gates?project_id=1

# Response:
{
  "task_id": 42,
  "status": "failed",  # or "passed"
  "failures": [
    {
      "gate": "tests",
      "reason": "3 tests failed",
      "details": "test_auth.py::test_login FAILED\n..."
    }
  ],
  "execution_time_seconds": 45.2
}
```

#### File Locations
```
codeframe/lib/quality_gates.py              # Core quality gate logic
codeframe/agents/worker_agent.py            # Pre-completion hooks
codeframe/persistence/database.py           # update_quality_gate_status()
web-ui/src/components/quality-gates/        # Frontend components
tests/lib/test_quality_gates.py             # Unit tests (150 tests)
tests/integration/test_quality_gates_integration.py  # Integration tests
```

### Checkpoint & Recovery System (User Story 3)

#### Creating Checkpoints
Checkpoints save full project state (Git + DB + context):

```python
from codeframe.lib.checkpoint_manager import CheckpointManager

checkpoint_mgr = CheckpointManager(project_path="/path/to/project", db=db)

# Create checkpoint
result = checkpoint_mgr.create_checkpoint(
    project_id=1,
    name="Before async refactor",
    description="Stable state before major refactoring",
    trigger="manual"
)

print(f"Checkpoint ID: {result['checkpoint_id']}")
print(f"Git commit: {result['git_commit']}")
print(f"DB backup: {result['database_backup_path']}")
```

#### Restoring Checkpoints
```python
# List checkpoints
checkpoints = checkpoint_mgr.list_checkpoints(project_id=1)
for cp in checkpoints:
    print(f"{cp.id}: {cp.name} ({cp.created_at})")

# Restore to checkpoint
result = checkpoint_mgr.restore_checkpoint(
    project_id=1,
    checkpoint_id=5,
    show_diff=True,  # Preview changes before restoring
    confirm=True
)

print(f"Restored to: {result['git_commit']}")
print(f"Files changed: {result['files_changed']}")
```

#### API Usage
```bash
# List checkpoints
GET /api/projects/1/checkpoints

# Create checkpoint
POST /api/projects/1/checkpoints
{
  "name": "Before async refactor",
  "description": "Stable state before major refactoring"
}

# Restore to checkpoint
POST /api/projects/1/checkpoints/5/restore
```

#### File Locations
```
codeframe/lib/checkpoint_manager.py         # Core checkpoint logic
codeframe/persistence/database.py           # save_checkpoint(), get_checkpoints()
codeframe/core/project.py                   # Project.resume() implementation
.codeframe/checkpoints/                     # Checkpoint storage
  ├── checkpoint-001.json                   # Metadata
  ├── checkpoint-001-db.sqlite              # Database backup
  └── checkpoint-001-context.json           # Context snapshot
tests/lib/test_checkpoint_manager.py        # Unit tests (110 tests)
tests/integration/test_checkpoint_restore.py  # Integration tests
```

### Metrics & Cost Tracking (User Story 5)

#### Recording Token Usage
Token usage is automatically recorded after every LLM API call:

```python
from codeframe.lib.metrics_tracker import MetricsTracker

tracker = MetricsTracker(db=db)

# Automatically called by WorkerAgent after LLM call
tracker.record_token_usage(
    task_id=42,
    agent_id="backend-001",
    project_id=1,
    model_name="claude-sonnet-4-5",
    input_tokens=1500,
    output_tokens=800,
    call_type="task_execution"
)

# Get project costs
costs = tracker.get_project_costs(project_id=1)
print(f"Total cost: ${costs['total_cost_usd']:.2f}")
print(f"By agent: {costs['by_agent']}")
print(f"By model: {costs['by_model']}")
```

#### Model Pricing (as of 2025-11)
```python
MODEL_PRICING = {
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},  # USD per million tokens
    "claude-opus-4": {"input": 15.00, "output": 75.00},
    "claude-haiku-4": {"input": 0.80, "output": 4.00}
}
```

#### API Usage
```bash
# Get token usage metrics
GET /api/projects/1/metrics/tokens?start_date=2025-11-01&end_date=2025-11-23

# Get cost metrics
GET /api/projects/1/metrics/costs

# Response:
{
  "total_cost_usd": 42.50,
  "by_agent": [
    {"agent_id": "backend-001", "cost_usd": 25.30},
    {"agent_id": "frontend-001", "cost_usd": 12.45}
  ],
  "by_model": [
    {"model": "claude-sonnet-4-5", "cost_usd": 38.00},
    {"model": "claude-haiku-4", "cost_usd": 4.50}
  ]
}
```

#### File Locations
```
codeframe/lib/metrics_tracker.py            # Core metrics logic
codeframe/agents/worker_agent.py            # Token tracking hooks
codeframe/persistence/database.py           # save_token_usage(), get_project_costs_aggregate()
web-ui/src/components/metrics/              # Frontend components
  ├── CostDashboard.tsx                     # Main cost dashboard
  ├── TokenUsageChart.tsx                   # Token usage visualization
  └── AgentMetrics.tsx                      # Per-agent metrics
tests/lib/test_metrics_tracker.py           # Unit tests (95 tests)
```

### End-to-End Testing (User Story 4)

#### TestSprite Integration
CodeFRAME uses TestSprite MCP for E2E test generation:

```bash
# Generate E2E test plan
cd tests/e2e
testsprite plan --scenario "Full workflow test" --output test_full_workflow.py

# Run E2E tests
pytest test_full_workflow.py -v

# Run Playwright frontend tests
playwright test
```

#### E2E Test Scenarios
1. **Full Workflow**: Discovery → Planning → Execution → Completion
2. **Quality Gates**: Task blocking on test failures, critical review findings
3. **Checkpoint/Restore**: Create checkpoint, modify files, restore successfully
4. **Review Agent**: Security issue detection, automatic task blocking
5. **Cost Tracking**: Token usage recorded accurately, costs calculated correctly

#### File Locations
```
tests/e2e/
├── test_full_workflow.py                   # Full workflow tests
├── test_quality_gates.py                   # Quality gate blocking tests
├── test_checkpoint_restore.py              # Checkpoint/restore tests
├── test_review_agent_analysis.py           # Review agent tests
├── test_cost_tracking_accuracy.py          # Metrics accuracy tests
└── fixtures/                               # Test fixtures
    └── hello_world_api/                    # Sample project for testing
```

### Performance Characteristics
- **Review Agent analysis**: <30s per file
- **Quality gate checks**: <2 minutes per task (all 4 stages)
- **Checkpoint creation**: <10s (includes Git commit + DB backup + context snapshot)
- **Checkpoint restoration**: <30s (includes Git checkout + DB restore + context load)
- **Token tracking**: <50ms per task update
- **Dashboard metrics load**: <200ms (real-time updates via WebSocket)

### Testing Summary
- **Backend Tests**: 355 tests (quality gates, checkpoints, metrics)
- **Frontend Tests**: 60 tests (components, API clients)
- **E2E Tests**: 120 tests (TestSprite + Playwright)
- **Total**: 535 Sprint 10 tests
- **Coverage**: 88%+ across all Sprint 10 components
- **Pass Rate**: 100%

### Best Practices

1. **Quality Gates**: Let gates run automatically on task completion; only bypass for emergency hotfixes
2. **Checkpoints**: Create checkpoints before major refactors, risky changes, or at phase transitions
3. **Cost Monitoring**: Check cost metrics daily to identify expensive agents/tasks
4. **E2E Testing**: Run E2E tests before every release to catch regressions

<!-- MANUAL ADDITIONS END -->
