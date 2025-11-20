# codeframe Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-11-14

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
- 010-server-start-command: Added CLI 'serve' command (--port, --reload, --no-browser flags), port validation utilities (port_utils.py), 19 tests with 100% coverage on utilities, no database changes
- 2025-11-14: 007-context-management - **CRITICAL ARCHITECTURAL FIX** 🎯
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

<!-- MANUAL ADDITIONS END -->
