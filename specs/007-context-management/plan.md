# Implementation Plan: Context Management

**Branch**: `007-context-management` | **Date**: 2025-11-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/007-context-management/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Implement a Virtual Project system for intelligent context management using tiered memory (HOT/WARM/COLD) with importance scoring. System enables long-running autonomous agent sessions (4+ hours) by reducing token usage 30-50% through strategic context archival and restoration. Core approach: calculate importance scores from item type, age decay, and access frequency; automatically tier items; checkpoint context when approaching token limits; restore with only HOT tier after flash save.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript 5.3+ (frontend dashboard)
**Primary Dependencies**: FastAPI, AsyncAnthropic, React 18, aiosqlite, tiktoken (for token counting)
**Storage**: SQLite with async support (aiosqlite) - context_items table schema already exists
**Testing**: pytest (backend with async fixtures), Jest/Vitest (frontend React components)
**Target Platform**: Linux server (WSL2 development environment)
**Project Type**: Web application (FastAPI backend + React frontend)
**Performance Goals**:
- Context tier lookup: <50ms
- Flash save operation: <2 seconds
- Importance score calculation: <10ms per item
- Context load (1000 items): <200ms

**Constraints**:
- Token reduction: 30-50% vs. full context loading
- Session duration: Support 4+ hour autonomous sessions
- Database: Maintain <100MB for context storage per agent
- Memory: Keep working context <50MB in RAM

**Scale/Scope**:
- Up to 10 concurrent worker agents
- 1000+ context items per agent (long-running sessions)
- Dashboard real-time updates for 100+ WebSocket connections
- Support multi-day autonomous project execution

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Test-First Development ✅
**Status**: PASS
**Compliance**: All context management features will follow TDD:
- Unit tests for importance scoring algorithm (before implementation)
- Integration tests for flash save workflow (before implementation)
- Component tests for dashboard visualization (before implementation)
- Red-Green-Refactor cycle enforced for all new code

### II. Async-First Architecture ✅
**Status**: PASS
**Compliance**: All I/O operations use async/await:
- `async def save_context_item()` - async database writes with aiosqlite
- `async def load_context()` - async database reads
- `async def flash_save()` - async checkpoint creation
- `async def update_tiers()` - async bulk tier reassignment
- No blocking SQLite calls - aiosqlite wrapper ensures async operations

### III. Context Efficiency ✅
**Status**: PASS - **THIS FEATURE IMPLEMENTS THIS PRINCIPLE**
**Compliance**: This feature directly implements Virtual Project system from constitution:
- HOT tier (always loaded): importance_score >= 0.8
- WARM tier (on-demand): 0.4 <= importance_score < 0.8
- COLD tier (archived): importance_score < 0.4
- Importance scoring: type weight × age decay × access boost
- Target: 30-50% token reduction (aligns with constitution goal)

### IV. Multi-Agent Coordination ✅
**Status**: PASS
**Compliance**: Context management supports multi-agent patterns:
- Per-agent context isolation via `agent_id` foreign key
- Shared SQLite state for context storage (aligns with Lead Agent coordination)
- No direct agent-to-agent context sharing
- Independent context tiers per worker agent

### V. Observability & Traceability ✅
**Status**: PASS
**Compliance**: All context operations are observable:
- WebSocket events for context tier changes (`context_tier_updated`)
- WebSocket events for flash save completion (`flash_save_completed`)
- Dashboard visualization of context breakdown (ContextPanel component)
- Database changelog tracks all context item modifications
- Structured logging: `logger.info(f"Agent {agent_id}: Flash save completed, {items_archived} items archived")`

### VI. Type Safety ✅
**Status**: PASS
**Compliance**: Type hints required throughout:
- Python: Type hints for all context methods (`async def save_context_item(self, item_type: str, content: str) -> int`)
- TypeScript: Strict mode for React components (`interface ContextPanelProps`)
- Pydantic models for API validation (`class ContextItemCreate(BaseModel)`)
- Database: Runtime validation via CHECK constraints (tier IN ('HOT', 'WARM', 'COLD'))

### VII. Incremental Delivery ✅
**Status**: PASS
**Compliance**: Feature split into independent stories:
- **P0 Story 1**: Context storage (independently testable)
- **P0 Story 2**: Importance scoring (builds on Story 1)
- **P0 Story 3**: Tier assignment (builds on Story 2)
- **P0 Story 4**: Flash save (integrates Stories 1-3)
- **P1 Story 5**: Dashboard visualization (optional enhancement)
- **P1 Story 6**: Context diffing (optional optimization)
- Each story delivers incremental value and can be deployed independently

**Overall Status**: ✅ **PASS** - No constitution violations. Feature aligns with all seven core principles.

## Project Structure

### Documentation (this feature)

```
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

**Structure Decision**: Web application (FastAPI backend + React frontend)

```
codeframe/
├── agents/
│   ├── worker_agent.py           # Add: save_context_item(), load_context(), flash_save()
│   ├── backend_worker_agent.py   # Add: context management integration
│   ├── frontend_worker_agent.py  # Add: context management integration
│   └── test_worker_agent.py      # Add: context management integration
├── persistence/
│   ├── database.py                # Add: context_items operations
│   └── migrations/
│       ├── migration_004_add_context_checkpoints.py  # NEW
│       └── migration_005_add_context_indexes.py      # NEW
├── lib/
│   ├── importance_scorer.py       # NEW: Importance calculation logic
│   ├── token_counter.py          # NEW: Token counting with tiktoken
│   └── context_manager.py        # NEW: Context tier management
└── ui/
    └── server.py                  # Add: Context API endpoints

web-ui/src/
├── components/
│   ├── ContextPanel.tsx          # NEW: Main context visualization
│   ├── ContextTierChart.tsx      # NEW: Tier distribution chart
│   └── ContextItemList.tsx       # NEW: Item list with scores
├── api/
│   └── context.ts                # NEW: Context API client
├── types/
│   └── context.ts                # NEW: TypeScript types for context
└── hooks/
    └── useContextStats.ts         # NEW: React hook for context stats

tests/
├── test_context_storage.py       # NEW: Context item CRUD tests
├── test_importance_scoring.py    # NEW: Scoring algorithm tests
├── test_tier_assignment.py       # NEW: Tier logic tests
├── test_flash_save.py            # NEW: Flash save integration tests
└── test_context_api.py           # NEW: API endpoint tests

web-ui/__tests__/
├── components/
│   ├── ContextPanel.test.tsx     # NEW
│   ├── ContextTierChart.test.tsx # NEW
│   └── ContextItemList.test.tsx  # NEW
└── api/
    └── context.test.ts            # NEW
```

**Key Additions**:
- **Backend**: 3 new library modules, 2 migrations, API endpoints in server.py
- **Frontend**: 3 React components, API client, TypeScript types
- **Tests**: 5 backend test files, 4 frontend test files
- **Total New Files**: ~15 files (excluding tests)

## Complexity Tracking

**Status**: ✅ **No Complexity Violations**

All constitution principles satisfied without exceptions. No complexity justification required.

