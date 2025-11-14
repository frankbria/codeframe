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

## Recent Changes
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
- 2025-11-14: 007-context-management Phase 2-5 complete - Context storage, scoring, and tier assignment ✅
  * Phase 2: Foundational layer (Pydantic models, migrations, database methods, TokenCounter)
  * Phase 3: Context item storage (save/load/get context with persistence)
  * Phase 4: Importance scoring with hybrid exponential decay algorithm (T027-T036)
  * Phase 5: Automatic tier assignment HOT/WARM/COLD (T037-T043, T046)
  * **Formula**: score = 0.4 × type_weight + 0.4 × age_decay + 0.2 × access_boost
  * **Tiers**: HOT (≥0.8), WARM (0.4-0.8), COLD (<0.4)
- 2025-11-14: 007-context-management - Implemented T012 and T013 database methods for context items and checkpoints
- 007-context-management: Added Python 3.11+ (backend), TypeScript 5.3+ (frontend dashboard) + FastAPI, AsyncAnthropic, React 18, aiosqlite, tiktoken (for token counting)
- 049-human-in-loop: Added Python 3.11+ (backend), TypeScript 5.3+ (frontend) + FastAPI, AsyncAnthropic, React 18, Tailwind CSS, aiosqlite, websockets
- 2025-11-08: Restructured documentation (SPRINTS.md, AGENTS.md, sprints/ directory)

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
<!-- MANUAL ADDITIONS END -->
